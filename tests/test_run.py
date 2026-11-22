"""End-to-end runs (fetch → normalize → dedupe → state) over the fixture config and a fake web."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
import pytest

from pipeline.__main__ import main
from pipeline.run import run

from .conftest import FIXTURE_CONFIG, FakeClock, FakeWeb

NOW = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.UTC)
LATER = NOW + dt.timedelta(hours=1)
WORLD = "https://feeds.example.com/world.xml"


def do_run(state: Path, web: FakeWeb, now: dt.datetime = NOW):
    return run(
        state, config_dir=FIXTURE_CONFIG, now=now, transport=web.transport, sleep=FakeClock().sleep
    )


def read(state: Path, name: str) -> dict:
    return json.loads((state / name).read_text())


def test_fetches_enabled_sources_only(tmp_path: Path) -> None:
    web = FakeWeb().serve_fixtures()
    report = do_run(tmp_path, web)

    assert sorted(report.outcomes) == [
        "example-gadgets",
        "example-hn",
        "example-reddit",
        "example-world",
    ]
    assert report.errors == {}
    assert not any("disabled" in u or "ExampleLeaks" in u for u in web.urls())
    assert len(report.entries) == 3 + 2 + 2 + 2  # world, gadgets, hn, reddit (min_score 50)


def test_health_and_cache_written(tmp_path: Path) -> None:
    web = FakeWeb().serve_fixtures(etag='"abc"')
    do_run(tmp_path, web)

    health = read(tmp_path, "source_health.json")
    assert health["example-world"] == {
        "consecutive_failures": 0,
        "feed_title": "Example Times > World",
        "last_attempt_at": "2026-11-21T12:00:00Z",
        "last_error": None,
        "last_error_at": None,
        "last_item_count": 3,
        "last_status": "ok",
        "last_success_at": "2026-11-21T12:00:00Z",
    }
    assert read(tmp_path, "http_cache.json")[WORLD] == {"etag": '"abc"', "last_modified": None}


def test_second_run_is_conditional_and_unchanged(tmp_path: Path) -> None:
    web = FakeWeb().serve_fixtures(etag='"abc"')
    do_run(tmp_path, web)
    web.requests.clear()

    report = do_run(tmp_path, web, now=LATER)
    assert all(r.headers.get("If-None-Match") == '"abc"' for r in web.requests)
    assert {o.status for o in report.outcomes.values()} == {"unchanged"}
    assert report.entries == []

    health = read(tmp_path, "source_health.json")["example-world"]
    assert health["last_status"] == "unchanged"
    assert health["last_item_count"] == 3  # kept from the last successful fetch
    assert health["feed_title"] == "Example Times > World"


def test_failing_source_is_recorded_and_others_continue(tmp_path: Path) -> None:
    web = FakeWeb().serve_fixtures()
    web.routes[WORLD] = lambda r: httpx.Response(503)
    report = do_run(tmp_path, web)

    assert report.errors == {"example-world": "HTTP 503 after 3 attempts"}
    assert "example-world" not in report.outcomes
    assert len(report.outcomes) == 3

    health = read(tmp_path, "source_health.json")["example-world"]
    assert health["last_status"] == "error"
    assert health["last_error"] == "HTTP 503 after 3 attempts"
    assert health["consecutive_failures"] == 1

    # the failure streak resets on the next success
    do_run(tmp_path, FakeWeb().serve_fixtures(), now=LATER)
    health = read(tmp_path, "source_health.json")["example-world"]
    assert health["consecutive_failures"] == 0
    assert health["last_error"] == "HTTP 503 after 3 attempts"  # history kept
    assert health["last_status"] == "ok"


def test_unparseable_feed_is_a_source_error(tmp_path: Path) -> None:
    web = FakeWeb().serve_fixtures()
    web.routes[WORLD] = lambda r: httpx.Response(200, content=b"<html>maintenance</html>")
    report = do_run(tmp_path, web)
    assert report.errors["example-world"].startswith("not a valid RSS/Atom feed")


def test_unexpected_exception_does_not_fail_run(tmp_path: Path, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("parser bug")

    monkeypatch.setattr("pipeline.fetch.reddit.parse_listing", boom)
    report = do_run(tmp_path, FakeWeb().serve_fixtures())
    assert report.errors == {"example-reddit": "unexpected RuntimeError: parser bug"}
    assert len(report.outcomes) == 3


def test_cli_invalid_config_exits_1(tmp_path: Path, capsys) -> None:
    (tmp_path / "topics.yaml").write_text("defaults: {}\n")
    code = main(["run", "--state", str(tmp_path / "state"), "--config-dir", str(tmp_path)])
    assert code == 1
    assert "Config invalid" in capsys.readouterr().err
    assert not (tmp_path / "state").exists()


# ───────────────────────────── items (normalize + exact dedupe) ─────────────────────────────


def read_items(state: Path) -> dict[str, dict]:
    rows = {}
    for path in sorted((state / "items").glob("*.ndjson")):
        for line in path.read_text().splitlines():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def snapshot(directory: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(directory)): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def test_items_are_stored_in_first_seen_partition(tmp_path: Path) -> None:
    report = do_run(tmp_path, FakeWeb().serve_fixtures())
    # 9 entries; the HN copy of the Freedonia story is an exact duplicate
    assert len(report.entries) == 9
    assert len(report.new_item_ids) == 8
    assert [p.name for p in (tmp_path / "items").iterdir()] == ["2026-11-21.ndjson"]

    items = read_items(tmp_path)
    assert len(items) == 8
    assert all(len(i["excerpt"] or "") <= 300 for i in items.values())
    freedonia = next(i for i in items.values() if "Freedonia" in i["title"])
    assert freedonia["source_id"] == "example-world"
    assert freedonia["also_covered_by"] == ["example-hn"]
    assert freedonia["canonical_url"] == (
        "https://www.example.com/2026/11/21/world/freedonia-coalition.html"
    )
    assert freedonia["excerpt"].startswith("Party leaders met for a third day")


def test_future_reddit_post_is_clamped_to_now(tmp_path: Path) -> None:
    do_run(tmp_path, FakeWeb().serve_fixtures())
    hearing = next(i for i in read_items(tmp_path).values() if "hearing" in i["title"])
    assert hearing["published_at"] == "2026-11-21T12:00:00Z"


def test_rerun_with_same_inputs_is_byte_identical(tmp_path: Path) -> None:
    do_run(tmp_path, FakeWeb().serve_fixtures())
    first = snapshot(tmp_path)
    report = do_run(tmp_path, FakeWeb().serve_fixtures())
    assert report.new_item_ids == []
    assert snapshot(tmp_path) == first


def test_later_rerun_keeps_items_unchanged(tmp_path: Path) -> None:
    do_run(tmp_path, FakeWeb().serve_fixtures())
    items_before = snapshot(tmp_path / "items")
    do_run(tmp_path, FakeWeb().serve_fixtures(), now=LATER)
    assert snapshot(tmp_path / "items") == items_before  # first_seen_at kept; no new partition


def test_old_entries_are_dropped_by_lookback(tmp_path: Path) -> None:
    report = do_run(tmp_path, FakeWeb().serve_fixtures(), now=NOW + dt.timedelta(days=8))
    titles = {i["title"] for i in read_items(tmp_path).values()}
    # only undated entries survive (their date defaults to the run time)
    assert titles == {"Item Without a Date"}
    assert len(report.new_item_ids) == 1


def test_crash_before_save_leaves_state_untouched(tmp_path: Path, monkeypatch) -> None:
    do_run(tmp_path, FakeWeb().serve_fixtures(etag='"abc"'))
    before = snapshot(tmp_path)

    def crash(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("pipeline.run.merge_exact", crash)
    with pytest.raises(RuntimeError):
        do_run(tmp_path, FakeWeb().serve_fixtures(etag='"new"'), now=LATER)
    assert snapshot(tmp_path) == before
