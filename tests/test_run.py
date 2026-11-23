"""End-to-end runs (fetch → normalize → dedupe → state) over the fixture config and a fake web."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import httpx
import pytest
import yaml

from pipeline.__main__ import main
from pipeline.process.embed import HashingEmbedder
from pipeline.run import run

from .conftest import FIXTURE_CONFIG, FakeClock, FakeWeb

NOW = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.UTC)
LATER = NOW + dt.timedelta(hours=1)
WORLD = "https://feeds.example.com/world.xml"


def do_run(state: Path, web: FakeWeb, now: dt.datetime = NOW):
    return run(
        state,
        config_dir=FIXTURE_CONFIG,
        now=now,
        transport=web.transport,
        sleep=FakeClock().sleep,
        embedder=HashingEmbedder(),
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
    assert len(report.entries) == 3 + 2 + 3 + 2  # world, gadgets, hn, reddit (min_score 50)


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
    # 10 entries; the HN copy of the Freedonia story is an exact duplicate
    assert len(report.entries) == 10
    assert len(report.new_item_ids) == 9
    assert [p.name for p in (tmp_path / "items").iterdir()] == ["2026-11-21.ndjson"]

    items = read_items(tmp_path)
    assert len(items) == 9
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


def test_excerpt_false_source_stores_no_excerpts(tmp_path: Path) -> None:
    do_run(tmp_path, FakeWeb().serve_fixtures())
    hn = [i for i in read_items(tmp_path).values() if i["source_id"] == "example-hn"]
    assert hn and all(i["excerpt"] is None for i in hn)


# ───────────────────────────── near-dup + relevance ─────────────────────────────


def test_near_duplicate_across_sources_is_hidden(tmp_path: Path) -> None:
    do_run(tmp_path, FakeWeb().serve_fixtures())
    items = read_items(tmp_path).values()
    sylvania = [i for i in items if "sylvania" in i["title"].lower()]
    assert len(sylvania) == 2
    kept = next(i for i in sylvania if i["hidden_reason"] != "duplicate")
    hidden = next(i for i in sylvania if i["hidden_reason"] == "duplicate")
    assert kept["source_id"] == "example-world"  # equal weights: stored first wins
    assert kept["also_covered_by"] == ["example-hn"]
    assert hidden["duplicate_of"] == kept["id"]
    assert hidden["topic_id"] is None  # duplicates aren't scored


def test_visible_new_items_get_topic_and_relevance(tmp_path: Path) -> None:
    do_run(tmp_path, FakeWeb().serve_fixtures())
    sources = {
        "example-world": {"world"},
        "example-gadgets": {"gadgets", "trackers"},
        "example-hn": {"gadgets", "politics"},
        "example-reddit": {"politics"},
    }
    for i in read_items(tmp_path).values():
        if i["hidden_reason"] == "duplicate":
            continue
        assert i["topic_id"] in sources[i["source_id"]]
        assert 0.0 <= i["relevance"] <= 1.0
        assert i["hidden_reason"] is None  # thresholds are applied at export, not stored


def test_no_new_items_means_no_embedding(tmp_path: Path) -> None:
    do_run(tmp_path, FakeWeb().serve_fixtures())

    class Exploding:
        def embed(self, texts, kind):
            raise AssertionError("embedder used with nothing new")

    report = run(
        tmp_path,
        config_dir=FIXTURE_CONFIG,
        now=LATER,
        transport=FakeWeb().serve_fixtures().transport,
        sleep=FakeClock().sleep,
        embedder=Exploding(),
    )
    assert report.new_item_ids == []


# ───────────────────────────── export ─────────────────────────────


def test_run_with_out_dir_exports_feed(tmp_path: Path) -> None:
    out = tmp_path / "site"
    run(tmp_path / "state", out_dir=out, config_dir=FIXTURE_CONFIG, now=NOW,
        transport=FakeWeb().serve_fixtures().transport, sleep=FakeClock().sleep,
        embedder=HashingEmbedder())  # fmt: skip
    index = json.loads((out / "feed" / "index.json").read_text())
    assert index["schema_version"] == 1
    assert index["generated_at"] == "2026-11-21T12:00:00Z"
    stored_visible = {  # fixture threshold 0.30, no skip sources, no corroboration needed
        i["id"]
        for i in read_items(tmp_path / "state").values()
        if i["hidden_reason"] is None and i["relevance"] >= 0.30
    }
    exported = {
        i["id"]
        for path in (out / "feed" / "topics").glob("*.json")
        for d in json.loads(path.read_text())["days"]
        for i in d["items"]
    }
    assert exported == stored_visible


def test_export_is_deterministic(tmp_path: Path) -> None:
    def once(name: str) -> dict[str, bytes]:
        out = tmp_path / name
        run(tmp_path / f"state-{name}", out_dir=out, config_dir=FIXTURE_CONFIG, now=NOW,
            transport=FakeWeb().serve_fixtures().transport, sleep=FakeClock().sleep,
            embedder=HashingEmbedder())  # fmt: skip
        return snapshot(out)

    assert once("a") == once("b")


def test_cli_run_with_out(tmp_path: Path, monkeypatch) -> None:
    calls = {}

    def fake_run(state, **kwargs):
        calls.update(kwargs, state=state)
        from pipeline.run import RunReport

        return RunReport()

    monkeypatch.setattr("pipeline.__main__.run", fake_run)
    assert main(["run", "--state", "s", "--out", "o", "--embedder", "hashing"]) == 0
    assert calls["state"] == Path("s") and calls["out_dir"] == Path("o")
    assert isinstance(calls["embedder"], HashingEmbedder)


def test_sample_feed_tool(tmp_path: Path) -> None:
    from pipeline.sample import main as sample_main

    assert sample_main(["--out", str(tmp_path)]) == 0
    index = json.loads((tmp_path / "feed" / "index.json").read_text())
    visible = sum(t["visible_count"] for g in index["groups"] for t in g["topics"])
    assert visible > 0  # threshold forced to 0, so the sample is never empty


def test_threshold_change_applies_on_next_run_without_new_items(tmp_path: Path) -> None:
    config = tmp_path / "config"
    shutil.copytree(FIXTURE_CONFIG, config)

    def exported(threshold: float) -> int:
        topics = yaml.safe_load((config / "topics.yaml").read_text())
        topics["defaults"]["relevance_threshold"] = threshold
        (config / "topics.yaml").write_text(yaml.safe_dump(topics, sort_keys=False))
        run(tmp_path / "state", out_dir=tmp_path / "site", config_dir=config, now=NOW,
            transport=FakeWeb().serve_fixtures().transport, sleep=FakeClock().sleep,
            embedder=HashingEmbedder())  # fmt: skip
        index = json.loads((tmp_path / "site" / "feed" / "index.json").read_text())
        return sum(t["visible_count"] + t["collapsed_count"] for g in index["groups"]
                   for t in g["topics"])  # fmt: skip

    strict = exported(0.99)
    lenient = exported(0.0)  # second run: nothing new, same stored scores
    assert strict < lenient
    assert lenient == sum(  # every non-duplicate stored item is exported
        1 for i in read_items(tmp_path / "state").values() if i["hidden_reason"] is None
    )


# ───────────────────────────── threads ─────────────────────────────


def test_run_threads_eligible_items(tmp_path: Path) -> None:
    report = do_run(tmp_path, FakeWeb().serve_fixtures())
    items = read_items(tmp_path)
    threads = {t["id"]: t for t in read(tmp_path, "threads.json")}
    modes = {"world": "threaded", "politics": "threaded", "trackers": "tracker", "gadgets": "flat"}
    for i in items.values():
        passes = i["hidden_reason"] is None and (i["relevance"] or 0) >= 0.30
        if modes.get(i["topic_id"]) in ("threaded", "tracker") and passes:
            assert i["thread_id"] in threads, i["title"]
            assert i["id"] in threads[i["thread_id"]]["item_ids"]
        elif modes.get(i["topic_id"]) == "flat":
            assert i["thread_id"] is None
    for t in threads.values():
        if t["topic_id"] == "trackers":
            assert t["id"].startswith("trackers--") and t["state"] == "active"
    assert report.threads.assigned == sum(1 for i in items.values() if i["thread_id"])
    assert set(read(tmp_path, "centroid_ids.json")) <= set(threads)


def test_rerun_without_new_items_leaves_threads_unchanged(tmp_path: Path) -> None:
    do_run(tmp_path, FakeWeb().serve_fixtures())
    before = snapshot(tmp_path)
    report = do_run(tmp_path, FakeWeb().serve_fixtures(), now=LATER)
    assert report.threads.assigned == 0
    for name in ("threads.json", "centroids.npy", "centroid_ids.json"):
        assert snapshot(tmp_path)[name] == before[name]
