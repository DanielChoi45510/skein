"""Owner overrides: the Worker document, fetch with fallback, state, lifecycle, export, run."""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

import httpx
import numpy as np
import pytest

from pipeline.config import load_config
from pipeline.export import export_feed
from pipeline.models import Item, Thread
from pipeline.overrides import EMPTY, MergeOp, Overrides, SplitOp, load_overrides
from pipeline.process.lifecycle import advance
from pipeline.state import OVERRIDES, State

from .conftest import FIXTURE_CONFIG

NOW = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.UTC)
H = dt.timedelta(hours=1)
D = dt.timedelta(days=1)
CFG = load_config(FIXTURE_CONFIG)
TOKEN = "pipeline-secret-token-value"
URL = "https://owner.example.workers.dev"

# Exactly what the Worker returns (worker/src/overrides.ts), plus a field from the future.
WORKER_DOC = {
    "version": 1,
    "updated_at": "2026-11-21T11:00:00.000Z",
    "threads": {
        "t1": {"title": "Gemini models", "pinned": True},
        "t2": {"muted": True},
    },
    "ops": [
        {"id": "op-a", "at": "2026-11-21T10:00:00.000Z", "type": "merge",
         "from": "t3", "into": "t1"},
        {"id": "op-b", "at": "2026-11-21T10:05:00.000Z", "type": "split", "thread": "t1",
         "items": ["i1"], "new_id": "uabcdefabcdef"},
        {"id": "op-c", "at": "2026-11-21T10:10:00.000Z", "type": "move", "item": "i2", "to": "t2"},
    ],
    "someday": "ignored",
}  # fmt: skip
DOC = Overrides.model_validate(WORKER_DOC)


# ───────────────────────────── the document ─────────────────────────────


def test_parses_the_worker_document() -> None:
    assert DOC.title("t1", "auto") == "Gemini models"
    assert DOC.title("t9", "auto") == "auto"
    assert DOC.pinned == {"t1"} and DOC.muted == {"t2"}
    merge, split, _ = DOC.ops
    assert isinstance(merge, MergeOp) and merge.from_ == "t3"
    assert isinstance(split, SplitOp) and split.new_id == "uabcdefabcdef"


def test_round_trips_with_the_worker_field_names() -> None:
    dumped = DOC.model_dump(mode="json", by_alias=True)
    assert dumped["ops"][0]["from"] == "t3"
    assert Overrides.model_validate(dumped) == DOC


# ───────────────────────────── fetch and fallback ─────────────────────────────


def worker(status: int = 200, body: object = WORKER_DOC, seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        content = body if isinstance(body, bytes) else json.dumps(body).encode()
        return httpx.Response(status, content=content)

    return httpx.MockTransport(handler)


ENV = {"WORKER_URL": URL + "/", "WORKER_PIPELINE_TOKEN": TOKEN}
SAVED = Overrides.model_validate({"threads": {"old": {"muted": True}}})


def test_fetches_from_the_worker_with_the_pipeline_token() -> None:
    seen: list[httpx.Request] = []
    got, origin = load_overrides(SAVED, ENV, transport=worker(seen=seen))
    assert (got, origin) == (DOC, "worker")
    [req] = seen
    assert str(req.url) == URL + "/overrides"
    assert req.headers["authorization"] == f"Bearer {TOKEN}"
    assert req.headers["user-agent"].startswith("Skein/")


@pytest.mark.parametrize(
    "transport",
    [
        pytest.param(worker(status=401), id="unauthorized"),
        pytest.param(worker(status=503), id="worker-down"),
        pytest.param(worker(body=b"<html>"), id="not-json"),
        pytest.param(worker(body={"version": 2}), id="unknown-version"),
        pytest.param(worker(body={"ops": [{"type": "explode"}]}), id="bad-op"),
    ],
)
def test_falls_back_to_the_saved_copy(transport, caplog) -> None:
    caplog.set_level(logging.WARNING)
    assert load_overrides(SAVED, ENV, transport=transport) == (SAVED, "saved")
    assert "using the saved copy" in caplog.text
    assert TOKEN not in caplog.text


def test_unreachable_worker_falls_back(caplog) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    caplog.set_level(logging.WARNING)
    assert load_overrides(SAVED, ENV, transport=httpx.MockTransport(boom)) == (SAVED, "saved")
    assert "unreachable (ConnectError)" in caplog.text
    assert TOKEN not in caplog.text


def test_without_worker_settings_uses_the_saved_copy_and_never_calls_out() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    transport = httpx.MockTransport(fail)
    assert load_overrides(SAVED, {}, transport=transport) == (SAVED, "saved")
    assert load_overrides(EMPTY, {}, transport=transport) == (EMPTY, "none")


def test_half_configured_is_warned_about(caplog) -> None:
    caplog.set_level(logging.WARNING)
    assert load_overrides(SAVED, {"WORKER_URL": URL}) == (SAVED, "saved")
    assert "must both be set" in caplog.text


# ───────────────────────────── state ─────────────────────────────


def test_state_saves_and_reloads_overrides(tmp_path: Path) -> None:
    state = State(tmp_path, NOW)
    assert state.overrides == EMPTY
    state.save()
    assert not (tmp_path / OVERRIDES).exists()  # nothing to keep yet

    state.overrides = DOC
    state.save()
    first = (tmp_path / OVERRIDES).read_bytes()
    assert json.loads(first)["ops"][0]["from"] == "t3"
    reloaded = State(tmp_path, NOW)
    assert reloaded.overrides == DOC
    reloaded.save()
    assert (tmp_path / OVERRIDES).read_bytes() == first  # byte-identical rerun


def test_unreadable_saved_overrides_start_empty(tmp_path: Path, caplog) -> None:
    (tmp_path / OVERRIDES).write_text('{"version": 7}')
    caplog.set_level(logging.WARNING)
    assert State(tmp_path, NOW).overrides == EMPTY
    assert "unreadable" in caplog.text


# ───────────────────────────── lifecycle ─────────────────────────────


def thread(thread_id: str, state: str = "active", *, last=NOW, topic: str = "world") -> Thread:
    return Thread(
        id=thread_id,
        topic_id=topic,
        kind="story",
        title=f"Auto {thread_id}",
        state=state,
        created_at=last - D,
        last_item_at=last,
        item_ids=["x"],
    )


def test_pinned_threads_never_archive() -> None:
    old = NOW - 90 * D  # fixture archive_after_days: 60
    threads = {"pin": thread("pin", last=old), "free": thread("free", last=old)}
    centroids = {k: np.ones(2, np.float32) for k in threads}
    advance(threads, centroids, {}, CFG.topics, NOW, pinned=frozenset({"pin"}))
    assert threads["pin"].state == "dormant" and "pin" in centroids
    assert threads["free"].state == "archived" and "free" not in centroids


# ───────────────────────────── export ─────────────────────────────


def item(n: int, thread_id: str | None = None, published=NOW, **kw) -> Item:
    fields = {
        "id": f"i{n:02d}",
        "source_id": "example-world",
        "url": f"https://example.com/{n}",
        "canonical_url": f"https://example.com/{n}",
        "title": f"Item {n}",
        "published_at": published,
        "first_seen_at": published,
        "topic_id": "world",
        "relevance": 0.5,
        "thread_id": thread_id,
    }
    return Item(**(fields | kw))


def export(tmp_path: Path, overrides: Overrides):
    threads = {t.id: t for t in [thread("t1"), thread("t2"), thread("t4", last=NOW - H)]}
    items = [
        item(1, "t1", NOW - 3 * H),
        item(2, "t2", NOW - 2 * H),
        item(3, "t2", NOW - 2 * H),
        item(4, "t4", NOW - H),
        item(5),
    ]
    index = export_feed(tmp_path, CFG, items, {}, NOW, threads=threads, overrides=overrides)
    feed_dir = tmp_path / "feed"
    topic = json.loads((feed_dir / "topics" / "world.json").read_text())
    files = {p.stem: json.loads(p.read_text()) for p in (feed_dir / "threads").glob("*.json")}
    world = next(t for g in index.groups for t in g.topics if t.id == "world")
    return topic, files, world


def test_export_without_overrides(tmp_path: Path) -> None:
    topic, files, world = export(tmp_path, EMPTY)
    assert [s["id"] for s in topic["threads"]] == ["t4", "t2", "t1"]  # newest update first
    assert not any(s["pinned"] for s in topic["threads"])
    assert topic["muted"] == []
    assert set(files) == {"t1", "t2", "t4"}
    assert world.visible_count == 5


def test_export_applies_rename_pin_and_mute(tmp_path: Path) -> None:
    topic, files, world = export(tmp_path, DOC)
    # t1 renamed and pinned first; t2 muted: not listed, no file, its items nowhere.
    assert [(s["id"], s["title"], s["pinned"]) for s in topic["threads"]] == [
        ("t1", "Gemini models", True),
        ("t4", "Auto t4", False),
    ]
    assert files["t1"]["title"] == "Gemini models"
    assert "t2" not in files
    exported = {i["id"] for d in topic["days"] for i in d["items"]} | {
        i["id"] for f in files.values() for d in f["days"] for i in d["items"]
    }
    assert exported == {"i01", "i04", "i05"}
    assert topic["muted"] == [{"id": "t2", "title": "Auto t2"}]
    assert world.visible_count == 3


def test_muted_list_uses_the_custom_title_and_skips_archived(tmp_path: Path) -> None:
    doc = Overrides.model_validate(
        {"threads": {"t2": {"muted": True, "title": "Quiet one"}, "t4": {"muted": True}}}
    )
    threads = {"t2": thread("t2"), "t4": thread("t4", "archived")}
    export_feed(tmp_path, CFG, [item(2, "t2")], {}, NOW, threads=threads, overrides=doc)
    topic = json.loads((tmp_path / "feed" / "topics" / "world.json").read_text())
    assert topic["muted"] == [{"id": "t2", "title": "Quiet one"}]


# ───────────────────────────── run ─────────────────────────────


def test_run_uses_saved_overrides_when_the_worker_is_not_configured(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    from pipeline.run import run

    from .conftest import FakeClock, FakeWeb

    monkeypatch.delenv("WORKER_URL", raising=False)
    monkeypatch.delenv("WORKER_PIPELINE_TOKEN", raising=False)
    state = tmp_path / "state"
    state.mkdir()
    (state / OVERRIDES).write_text(json.dumps(WORKER_DOC))
    caplog.set_level(logging.INFO)
    from pipeline.process.embed import HashingEmbedder

    run(state, config_dir=FIXTURE_CONFIG, now=NOW, transport=FakeWeb().serve_fixtures().transport,
        sleep=FakeClock().sleep, embedder=HashingEmbedder())  # fmt: skip
    assert "overrides (saved): 1 renamed, 1 pinned, 1 muted, 3 op(s)" in caplog.text
    assert State(state, NOW).overrides == DOC  # kept for the next run


def test_run_survives_an_unreachable_worker(tmp_path: Path, monkeypatch) -> None:
    import pipeline.overrides as overrides_mod
    from pipeline.process.embed import HashingEmbedder
    from pipeline.run import run

    from .conftest import FakeClock, FakeWeb

    monkeypatch.setenv("WORKER_URL", URL)
    monkeypatch.setenv("WORKER_PIPELINE_TOKEN", TOKEN)
    monkeypatch.setattr(overrides_mod, "fetch_overrides", lambda *a, **k: None)
    report = run(tmp_path, config_dir=FIXTURE_CONFIG, now=NOW,
                 transport=FakeWeb().serve_fixtures().transport, sleep=FakeClock().sleep,
                 embedder=HashingEmbedder())  # fmt: skip
    assert report.new_item_ids  # the run finished normally


def test_run_applies_ops_once_and_reruns_are_byte_identical(tmp_path: Path, monkeypatch) -> None:
    import shutil

    import yaml

    from pipeline.process.embed import HashingEmbedder
    from pipeline.run import run
    from pipeline.state import OVERRIDES_APPLIED

    from .conftest import FakeClock, FakeWeb

    monkeypatch.delenv("WORKER_URL", raising=False)
    monkeypatch.delenv("WORKER_PIPELINE_TOKEN", raising=False)
    # Hashing-embedder scores are meaningless: threshold 0 so items get threads.
    config = tmp_path / "config"
    shutil.copytree(FIXTURE_CONFIG, config)
    topics = yaml.safe_load((config / "topics.yaml").read_text())
    topics["defaults"]["relevance_threshold"] = 0.0
    (config / "topics.yaml").write_text(yaml.safe_dump(topics, sort_keys=False))
    tmp_path = tmp_path / "state"
    tmp_path.mkdir()

    def once(now: dt.datetime):
        return run(tmp_path, config_dir=config, now=now,
                   transport=FakeWeb().serve_fixtures().transport, sleep=FakeClock().sleep,
                   embedder=HashingEmbedder())  # fmt: skip

    once(NOW)
    first = State(tmp_path, NOW)
    world = sorted((t for t in first.threads.values() if t.topic_id == "world"), key=lambda t: t.id)
    target, other = world[0], world[1]
    moving = other.item_ids[0]
    doc = {"ops": [{"id": "op-1", "at": "2026-11-21T12:30:00Z", "type": "move",
                    "item": moving, "to": target.id}]}  # fmt: skip
    (tmp_path / OVERRIDES).write_text(json.dumps(doc))

    report = once(NOW + H)
    assert (report.threads.ops_applied, report.threads.ops_skipped) == (1, 0)
    after = State(tmp_path, NOW + H)
    assert after.items[moving].thread_id == target.id
    assert after.threads[target.id].state == "active"
    assert json.loads((tmp_path / OVERRIDES_APPLIED).read_text()) == {"op-1": "applied"}

    snapshot = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    report = once(NOW + H)
    assert report.threads.ops_applied == 0
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == snapshot
