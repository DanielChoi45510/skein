"""Owner merge / split / move (DESIGN §10.2): applied once, in order, with skips recorded."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from pipeline.config import load_config
from pipeline.models import Item, Thread
from pipeline.overrides import Overrides
from pipeline.process.lifecycle import _default_title
from pipeline.process.structural import apply_ops, prune_applied

from ..conftest import FIXTURE_CONFIG

NOW = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.UTC)
H = dt.timedelta(hours=1)
CFG = load_config(FIXTURE_CONFIG)
TOPICS = {t.id: t for t in CFG.topics.topics}

# Item id → unit vector, so recomputed centroids are exact.
AXES = {"a1": 0, "a2": 0, "b1": 1, "b2": 1, "c1": 2, "p1": 3, "p2": 3, "x1": 4}


def vec(item_id: str) -> np.ndarray:
    v = np.zeros(5, np.float32)
    v[AXES[item_id]] = 1.0
    return v


def item(item_id: str, thread_id: str | None, topic: str = "world", age_h: float = 1) -> Item:
    at = NOW - age_h * H
    return Item(
        id=item_id,
        source_id="example-world",
        url=f"https://example.com/{item_id}",
        canonical_url=f"https://example.com/{item_id}",
        title=f"Story {item_id[0].upper()} update {item_id}",
        published_at=at,
        first_seen_at=at,
        topic_id=topic,
        relevance=0.9,
        thread_id=thread_id,
    )


def thread(thread_id: str, item_ids: list[str], state="active", topic="world", kind="story"):
    return Thread(
        id=thread_id,
        topic_id=topic,
        kind=kind,
        title=f"Auto {thread_id}",
        state=state,
        created_at=NOW - 5 * H,
        last_item_at=NOW - 2 * H,
        item_ids=list(item_ids),
    )


class World:
    """Threads A (a1, a2), B (b1, b2), C (c1, pending); trackers Phones (p1, p2), Laptops."""

    def __init__(self) -> None:
        self.items = {
            i.id: i
            for i in [
                item("a1", "A", age_h=3), item("a2", "A", age_h=2),
                item("b1", "B", age_h=4), item("b2", "B", age_h=1),
                item("c1", "C"), item("x1", None),
                item("p1", "trackers--phones", "trackers"),
                item("p2", "trackers--phones", "trackers"),
            ]
        }  # fmt: skip
        self.threads = {
            t.id: t
            for t in [
                thread("A", ["a1", "a2"]),
                thread("B", ["b1", "b2"]),
                thread("C", ["c1"], state="pending"),
                thread("trackers--phones", ["p1", "p2"], topic="trackers", kind="tracker"),
                thread("trackers--laptops", [], topic="trackers", kind="tracker"),
            ]
        }
        self.centroids = {t: np.ones(5, np.float32) / np.sqrt(5) for t in ("A", "B", "C")}
        self.applied: dict[str, str] = {}
        self.embedded: list[list[str]] = []

    def embed(self, items: list[Item]) -> dict[str, np.ndarray]:
        self.embedded.append(sorted(i.id for i in items))
        return {i.id: vec(i.id) for i in items}

    def apply(self, *ops: dict):
        doc = Overrides.model_validate({"ops": list(ops)})
        return apply_ops(
            doc.ops, self.applied, self.items, self.threads, self.centroids, TOPICS,
            embed=self.embed, title_of=_default_title,
        )  # fmt: skip


def op(n: int, **fields) -> dict:
    return {"id": f"op{n}", "at": (NOW + n * dt.timedelta(seconds=1)).isoformat(), **fields}


# ───────────────────────────── merge ─────────────────────────────


def test_merge_moves_every_item_and_deletes_the_source() -> None:
    w = World()
    report = w.apply(op(1, type="merge", **{"from": "B"}, into="A"))
    assert (report.applied, report.skipped) == (1, 0)
    assert "B" not in w.threads and "B" not in w.centroids
    assert w.threads["A"].item_ids == ["a1", "a2", "b1", "b2"]
    assert {w.items[i].thread_id for i in ("b1", "b2")} == {"A"}
    assert w.threads["A"].last_item_at == w.items["b2"].published_at
    # Centroid: plain mean of a1, a2 (axis 0) and b1, b2 (axis 1).
    np.testing.assert_allclose(w.centroids["A"], np.array([1, 1, 0, 0, 0]) / np.sqrt(2), atol=1e-6)
    assert w.applied == {"op1": "applied"}


def test_merge_into_a_pending_thread_activates_it() -> None:
    w = World()
    w.apply(op(1, type="merge", **{"from": "A"}, into="C"))
    assert w.threads["C"].state == "active"
    assert w.threads["C"].item_ids == ["c1", "a1", "a2"]


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"from": "Z", "into": "A"}, "source thread Z is gone"),
        ({"from": "A", "into": "Z"}, "target thread Z is gone"),
        ({"from": "A", "into": "trackers--phones"}, "different topics"),
        ({"from": "trackers--laptops", "into": "trackers--phones"}, "only possible in threaded"),
    ],
)
def test_merge_skips(fields: dict, reason: str) -> None:
    w = World()
    report = w.apply(op(1, type="merge", **fields))
    assert report.skipped == 1
    assert reason in w.applied["op1"] and w.applied["op1"].startswith("skipped: ")
    assert set(w.threads) == {"A", "B", "C", "trackers--phones", "trackers--laptops"}


def test_merge_into_an_archived_thread_is_skipped() -> None:
    w = World()
    w.threads["B"].state = "archived"
    w.apply(op(1, type="merge", **{"from": "A"}, into="B"))
    assert w.applied["op1"] == "skipped: target thread B is gone"


# ───────────────────────────── split ─────────────────────────────


def test_split_creates_a_thread_with_the_listed_items() -> None:
    w = World()
    w.apply(op(1, type="split", thread="A", items=["a2", "zz", "b1"], new_id="unew"))
    new = w.threads["unew"]
    assert new.item_ids == ["a2"]  # zz isn't loaded, b1 isn't in A
    assert (new.state, new.topic_id, new.kind) == ("active", "world", "story")
    assert w.items["a2"].thread_id == "unew"
    assert w.threads["A"].item_ids == ["a1"]
    assert new.title == "Story A update a2"  # one item: its headline
    np.testing.assert_allclose(w.centroids["unew"], vec("a2"))
    assert sorted(w.embedded[0]) == ["a1", "a2"]  # only the affected threads' items


def test_split_taking_every_item_deletes_the_source() -> None:
    w = World()
    w.apply(op(1, type="split", thread="B", items=["b1", "b2"], new_id="unew"))
    assert "B" not in w.threads and "B" not in w.centroids
    assert w.threads["unew"].item_ids == ["b1", "b2"]


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"thread": "A", "items": ["b1"], "new_id": "unew"}, "none of the items"),
        ({"thread": "A", "items": ["a1"], "new_id": "B"}, "thread B already exists"),
        ({"thread": "Z", "items": ["a1"], "new_id": "unew"}, "source thread Z is gone"),
        ({"thread": "trackers--phones", "items": ["p1"], "new_id": "unew"}, "only possible"),
    ],
)
def test_split_skips(fields: dict, reason: str) -> None:
    w = World()
    w.apply(op(1, type="split", **fields))
    assert reason in w.applied["op1"]
    assert "unew" not in w.threads


# ───────────────────────────── move ─────────────────────────────


def test_move_between_threads() -> None:
    w = World()
    w.apply(op(1, type="move", item="a1", to="B"))
    assert w.threads["A"].item_ids == ["a2"] and w.threads["B"].item_ids == ["b1", "b2", "a1"]
    assert w.items["a1"].thread_id == "B"
    assert w.items["a1"].owner_placed  # re-routing never undoes a hand placement
    assert not w.items["a2"].owner_placed
    np.testing.assert_allclose(w.centroids["A"], vec("a2"))


def test_move_a_single_item_into_a_thread() -> None:
    w = World()
    w.apply(op(1, type="move", item="x1", to="A"))
    assert w.items["x1"].thread_id == "A" and "x1" in w.threads["A"].item_ids


def test_move_emptying_an_automatic_thread_deletes_it() -> None:
    w = World()
    w.apply(op(1, type="move", item="c1", to="A"))
    assert "C" not in w.threads and "C" not in w.centroids


def test_move_between_tracker_threads_keeps_both() -> None:
    w = World()
    w.apply(op(1, type="move", item="p1", to="trackers--laptops"),
            op(2, type="move", item="p2", to="trackers--laptops"))  # fmt: skip
    assert w.threads["trackers--laptops"].item_ids == ["p1", "p2"]
    assert w.threads["trackers--phones"].item_ids == []  # predefined threads stay
    assert w.applied == {"op1": "applied", "op2": "applied"}
    assert "trackers--laptops" not in w.centroids  # tracker threads have no centroid
    assert w.embedded == []


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"item": "zz", "to": "A"}, "item zz is gone"),
        ({"item": "a1", "to": "Z"}, "target thread Z is gone"),
        ({"item": "a1", "to": "trackers--phones"}, "different topic"),
        ({"item": "a1", "to": "A"}, "already in that thread"),
    ],
)
def test_move_skips(fields: dict, reason: str) -> None:
    w = World()
    w.apply(op(1, type="move", **fields))
    assert reason in w.applied["op1"]


# ───────────────────────────── once, in order ─────────────────────────────


def test_ops_apply_once_in_order() -> None:
    w = World()
    # Listed out of order: the split (op1) must run before the merge of its result (op2).
    ops = [
        op(2, type="merge", **{"from": "unew"}, into="B"),
        op(1, type="split", thread="A", items=["a1"], new_id="unew"),
    ]
    w.apply(*ops)
    assert w.applied == {"op1": "applied", "op2": "applied"}
    assert w.threads["B"].item_ids == ["b1", "b2", "a1"]
    snapshot = {k: t.model_dump() for k, t in w.threads.items()}
    report = w.apply(*ops)
    assert (report.applied, report.skipped) == (0, 0)
    assert {k: t.model_dump() for k, t in w.threads.items()} == snapshot


def test_prune_forgets_ops_the_worker_no_longer_lists() -> None:
    applied = {"op1": "applied", "old": "applied", "gone": "skipped: x"}
    doc = Overrides.model_validate({"ops": [op(1, type="move", item="a1", to="B")]})
    prune_applied(applied, doc.ops)
    assert applied == {"op1": "applied"}
