"""Thread assignment for a run (DESIGN §6.5): selection, attach / new, rescue, backfill."""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Sequence

import numpy as np
import pytest

from pipeline.config import load_config
from pipeline.config.validate import Config
from pipeline.models import Item, Thread
from pipeline.process.thread_assign import assign_threads, select
from pipeline.process.threads import new_thread_id

from ..conftest import FIXTURE_CONFIG

NOW = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.UTC)
H = dt.timedelta(hours=1)
D = dt.timedelta(days=1)
CFG = load_config(FIXTURE_CONFIG)  # relevance threshold 0.30; world, politics: threaded

# Keyword → axis, so similarities are exact: same keyword 1.0, different 0.0.
AXES = ["alpha", "beta", "gamma", "phone", "laptop", "energy", "rates"]


class AxisEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: Sequence[str], kind: str) -> np.ndarray:
        self.calls.append(list(texts))
        out = np.zeros((len(texts), len(AXES) + 1), np.float32)
        for row, text in enumerate(texts):
            for axis, word in enumerate(AXES):
                out[row, axis] = text.lower().count(word)
            if not out[row].any():
                out[row, -1] = 1.0
        return out / np.linalg.norm(out, axis=1, keepdims=True)


def item(n: int, title: str, *, topic: str = "world", rel: float = 0.9, at=NOW, **kw) -> Item:
    source = {"trackers": "example-gadgets", "politics": "example-reddit"}.get(
        topic, "example-world"
    )
    fields = {
        "id": f"i{n:02d}",
        "source_id": source,
        "url": f"https://example.com/{n}",
        "canonical_url": f"https://example.com/{n}",
        "title": title,
        "published_at": at,
        "first_seen_at": at,
        "topic_id": topic,
        "relevance": rel,
    }
    return Item(**(fields | kw))


class Run:
    """State for repeated assign_threads calls, like the pipeline's State."""

    def __init__(self, cfg: Config = CFG) -> None:
        self.cfg = cfg
        self.items: dict[str, Item] = {}
        self.threads: dict[str, Thread] = {}
        self.centroids: dict[str, np.ndarray] = {}
        self.embedder = AxisEmbedder()
        self.loads = 0

    def get_embedder(self) -> AxisEmbedder:
        self.loads += 1
        return self.embedder

    def __call__(self, new: list[Item], now: dt.datetime = NOW, *, with_vectors: bool = True):
        for i in new:
            self.items[i.id] = i
        vectors = {}
        if with_vectors and new:
            vecs = AxisEmbedder().embed([i.title for i in new], "passage")
            vectors = dict(zip([i.id for i in new], vecs, strict=True))
        return assign_threads(
            self.items,
            self.threads,
            self.centroids,
            self.cfg,
            now,
            new_ids={i.id for i in new},
            vectors=vectors,
            get_embedder=self.get_embedder,
        )


# ───────────────────────────── automatic threads ─────────────────────────────


def test_similar_items_share_a_thread_which_is_promoted() -> None:
    run = Run()
    report = run([item(1, "Alpha talks open", at=NOW - 2 * H), item(2, "Alpha talks stall")])
    a, b = run.items["i01"], run.items["i02"]
    assert a.thread_id == b.thread_id == new_thread_id("world", "i01")
    thread = run.threads[a.thread_id]
    assert thread.state == "active"  # 2nd item within 72 h
    assert thread.item_ids == ["i01", "i02"]
    assert thread.title == "Alpha · Talks"
    assert thread.kind == "story"
    assert b.thread_score == pytest.approx(1.0)
    assert (report.created, report.attached, report.assigned) == (1, 1, 2)


def test_dissimilar_items_start_separate_pending_threads() -> None:
    run = Run()
    run([item(1, "Alpha news"), item(2, "Beta news")])
    assert run.items["i01"].thread_id != run.items["i02"].thread_id
    assert {t.state for t in run.threads.values()} == {"pending"}
    assert run.threads[run.items["i02"].thread_id].title == "Beta news"


def test_topics_never_share_threads() -> None:
    run = Run()
    run([item(1, "Alpha in world"), item(2, "Alpha in politics", topic="politics")])
    assert run.items["i01"].thread_id != run.items["i02"].thread_id


def test_items_join_threads_from_earlier_runs() -> None:
    run = Run()
    run([item(1, "Gamma plan")], NOW - D)
    run([item(2, "Gamma plan passes")], NOW)
    assert run.items["i02"].thread_id == run.items["i01"].thread_id
    assert "i02" in run.threads[run.items["i01"].thread_id].item_ids


def test_pending_thread_is_not_joined_after_72_hours() -> None:
    run = Run()
    old = NOW - 4 * D
    run([item(1, "Gamma plan", at=old)], old)
    run([item(2, "Gamma plan passes")], NOW)
    assert run.items["i02"].thread_id != run.items["i01"].thread_id


def test_flat_topics_and_ineligible_items_are_not_threaded() -> None:
    run = Run()
    disabled = item(4, "Alpha disabled", source_id="example-disabled")
    old = item(5, "Alpha old", at=NOW - 8 * D)  # fixture lookback: 7 days
    dup = item(6, "Alpha dup", hidden_reason="duplicate", duplicate_of="i01")
    run([
        item(1, "Alpha"),
        item(2, "Desk lamp", topic="gadgets"),
        item(3, "Alpha low", rel=0.1),
        disabled, old, dup,
    ])  # fmt: skip
    threaded = {i.id for i in run.items.values() if i.thread_id}
    assert threaded == {"i01"}


def test_title_excluded_items_are_not_threaded() -> None:
    sources = [
        s.model_copy(update={"title_exclude": ["quote page"]}) if s.id == "example-world" else s
        for s in CFG.sources.sources
    ]
    cfg = dataclasses.replace(CFG, sources=CFG.sources.model_copy(update={"sources": sources}))
    run = Run(cfg)
    run([item(1, "Alpha quote page")])
    assert run.items["i01"].thread_id is None


# ───────────────────────────── tracker and fixed ─────────────────────────────


def test_tracker_items_route_to_predefined_threads_only() -> None:
    run = Run()
    report = run([
        item(1, "New phone review", topic="trackers"),
        item(2, "Laptop review", topic="trackers"),
        item(3, "Another phone", topic="trackers"),
        item(4, "Something else", topic="trackers"),  # still attaches somewhere
    ])  # fmt: skip
    ids = {i.id: i.thread_id for i in run.items.values()}
    assert ids["i01"] == ids["i03"] == "trackers--phones"
    assert ids["i02"] == "trackers--laptops"
    assert ids["i04"] in ("trackers--phones", "trackers--laptops")
    assert set(run.threads) == {"trackers--phones", "trackers--laptops"}
    phones = run.threads["trackers--phones"]
    assert (phones.kind, phones.state, phones.title) == ("tracker", "active", "Phones")
    assert run.centroids == {}  # anchors come from config, not stored
    assert report.predefined == 4 and report.created == 0


# ───────────────────────────── rescue ─────────────────────────────


def test_rescue_attaches_new_near_miss_to_active_thread() -> None:
    run = Run()
    run([item(1, "Alpha opens", at=NOW - 3 * H), item(2, "Alpha grows", at=NOW - 2 * H)])
    report = run([item(3, "Alpha terse", rel=0.27)])  # threshold 0.30, band 0.25
    assert run.items["i03"].thread_id == run.items["i01"].thread_id
    assert run.items["i03"].thread_score == pytest.approx(1.0)
    assert report.rescued == 1


def test_rescue_never_creates_or_joins_pending_threads() -> None:
    run = Run()
    run([item(1, "Alpha alone", at=NOW - H)])  # pending
    run([item(2, "Alpha terse", rel=0.27), item(3, "Beta terse", rel=0.27)])
    assert run.items["i02"].thread_id is None
    assert run.items["i03"].thread_id is None
    assert len(run.threads) == 1


def test_stored_near_misses_are_not_reconsidered() -> None:
    run = Run()
    run([item(1, "Alpha opens", at=NOW - 3 * H), item(2, "Alpha grows", at=NOW - 2 * H)])
    run.items["i03"] = item(3, "Alpha terse", rel=0.27)  # stored, not new this run
    run([])
    assert run.items["i03"].thread_id is None
    assert run.loads == 0


# ───────────────────────────── backfill and determinism ─────────────────────────────


def test_backfill_embeds_stored_unthreaded_items_once() -> None:
    run = Run()
    run.items.update({i.id: i for i in [item(1, "Alpha a"), item(2, "Alpha b")]})
    report = run([])
    assert report.backfilled == 2
    assert run.items["i01"].thread_id == run.items["i02"].thread_id
    assert run.loads == 1

    report = run([])  # nothing left to do: the model isn't needed
    assert report.backfilled == 0 and report.assigned == 0
    assert run.loads == 1


def test_new_items_reuse_their_vectors() -> None:
    run = Run()
    run([item(1, "Alpha")])
    assert run.loads == 0


def test_assignment_is_deterministic() -> None:
    items = [item(n, t, at=NOW - n * H) for n, t in enumerate(
        ["Alpha x", "Beta y", "Alpha z", "Gamma", "Beta again", "Alpha w"], 1)]  # fmt: skip
    one, two = Run(), Run()
    one([i.model_copy() for i in items])
    two([i.model_copy() for i in reversed(items)])
    assert one.threads == two.threads
    assert {k: v.tolist() for k, v in one.centroids.items()} == {
        k: v.tolist() for k, v in two.centroids.items()
    }


def test_select_orders_by_publication() -> None:
    items = {
        i.id: i for i in [item(2, "b", at=NOW - H), item(1, "a", at=NOW), item(3, "c", rel=0.27)]
    }
    assign, band = select(items, CFG, new_ids={"i03"}, now=NOW)
    assert [i.id for i in assign] == ["i02", "i01"]
    assert [i.id for i in band] == ["i03"]
