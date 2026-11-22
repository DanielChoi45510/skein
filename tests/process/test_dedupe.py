"""Exact and near-duplicate deduplication."""

from __future__ import annotations

import datetime as dt

import numpy as np

from pipeline.models import Item
from pipeline.process.dedupe import NEAR_DUP_THRESHOLD, mark_near_duplicates, merge_exact

T0 = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.UTC)
H = dt.timedelta(hours=1)


def item(id: str, source: str = "a", published: dt.datetime = T0, **kw) -> Item:
    fields = {
        "id": id,
        "source_id": source,
        "url": f"https://{source}.example/{id}",
        "canonical_url": f"https://{source}.example/{id}",
        "title": f"title {id} from {source}",
        "published_at": published,
        "first_seen_at": T0,
    }
    return Item(**(fields | kw))


def vec(cos: float) -> np.ndarray:
    """A unit vector whose cosine with [1, 0] is `cos`."""
    return np.array([cos, np.sqrt(max(0.0, 1 - cos**2))])


BASE = np.array([1.0, 0.0])


# ───────────────────────────── exact ─────────────────────────────


def test_new_items_are_added() -> None:
    store: dict[str, Item] = {}
    assert merge_exact(store, [item("x"), item("y")], {}) == ["x", "y"]
    assert set(store) == {"x", "y"}


def test_same_source_repeat_is_noop() -> None:
    store = {"x": item("x")}
    before = store["x"].model_copy(deep=True)
    assert merge_exact(store, [item("x", title="changed headline")], {}) == []
    assert store["x"] == before


def test_other_source_adds_corroboration() -> None:
    store = {"x": item("x", source="a")}
    merge_exact(store, [item("x", source="b"), item("x", source="c")], {})
    assert store["x"].source_id == "a"
    assert store["x"].also_covered_by == ["b", "c"]
    # and again: still idempotent
    merge_exact(store, [item("x", source="b")], {})
    assert store["x"].also_covered_by == ["b", "c"]


def test_higher_weight_source_takes_over() -> None:
    store = {"x": item("x", source="a", extra={"score": 1})}
    merge_exact(store, [item("x", source="b", extra={"k": "v"})], {"a": 1.0, "b": 1.3})
    kept = store["x"]
    assert kept.source_id == "b"
    assert kept.title == "title x from b"
    assert kept.extra == {"k": "v"}
    assert kept.also_covered_by == ["a"]
    assert kept.first_seen_at == T0  # history kept
    # re-seeing either source changes nothing
    snapshot = kept.model_copy(deep=True)
    merge_exact(store, [item("x", source="a"), item("x", source="b")], {"a": 1.0, "b": 1.3})
    assert store["x"] == snapshot


def test_equal_weight_keeps_first() -> None:
    store: dict[str, Item] = {}
    merge_exact(store, [item("x", source="a"), item("x", source="b")], {"a": 1.0, "b": 1.0})
    assert store["x"].source_id == "a"
    assert store["x"].also_covered_by == ["b"]


def test_exact_match_on_hidden_duplicate_credits_kept_item() -> None:
    store = {
        "kept": item("kept", source="a"),
        "dup": item("dup", source="b", duplicate_of="kept", hidden_reason="duplicate"),
    }
    merge_exact(store, [item("dup", source="c")], {})
    assert store["dup"].also_covered_by == ["c"]
    assert store["kept"].also_covered_by == ["c"]


# ───────────────────────────── near-duplicate ─────────────────────────────


def test_near_duplicate_hidden_and_corroborates() -> None:
    store = {"old": item("old", source="a"), "new": item("new", source="b", published=T0 + H)}
    pairs = mark_near_duplicates(store, ["new"], {"old": BASE, "new": vec(0.95)}, {})
    assert pairs == [("new", "old")]
    assert store["new"].hidden_reason == "duplicate"
    assert store["new"].duplicate_of == "old"
    assert store["old"].visible
    assert store["old"].also_covered_by == ["b"]


def test_threshold_is_inclusive() -> None:
    at = {"old": item("old"), "new": item("new", source="b")}
    assert mark_near_duplicates(at, ["new"], {"old": BASE, "new": vec(NEAR_DUP_THRESHOLD)}, {})
    below = {"old": item("old"), "new": item("new", source="b")}
    assert not mark_near_duplicates(below, ["new"], {"old": BASE, "new": vec(0.919)}, {})
    assert below["new"].visible


def test_outside_48h_window_is_not_a_duplicate() -> None:
    store = {"old": item("old"), "new": item("new", published=T0 + 49 * H)}
    assert mark_near_duplicates(store, ["new"], {"old": BASE, "new": BASE}, {}) == []


def test_higher_weight_new_item_wins() -> None:
    store = {
        "old": item("old", source="a"),
        "older-dup": item("older-dup", source="c", duplicate_of="old", hidden_reason="duplicate"),
        "new": item("new", source="b"),
    }
    pairs = mark_near_duplicates(store, ["new"], {"old": BASE, "new": BASE}, {"b": 1.5})
    assert pairs == [("old", "new")]
    assert store["old"].hidden_reason == "duplicate"
    assert store["new"].visible
    assert store["new"].also_covered_by == ["a"]
    # items that pointed at the loser now point at the winner
    assert store["older-dup"].duplicate_of == "new"


def test_same_source_near_duplicate_keeps_earlier_without_self_corroboration() -> None:
    store = {"v1": item("v1", source="a"), "v2": item("v2", source="a")}
    mark_near_duplicates(store, ["v2"], {"v1": BASE, "v2": BASE}, {})
    assert store["v2"].duplicate_of == "v1"
    assert store["v1"].also_covered_by == []


def test_hidden_items_are_not_match_targets() -> None:
    store = {
        "hidden": item("hidden", hidden_reason="below_threshold"),
        "new": item("new", source="b"),
    }
    assert mark_near_duplicates(store, ["new"], {"hidden": BASE, "new": BASE}, {}) == []


def test_new_items_in_one_run_dedupe_against_each_other_in_order() -> None:
    store = {"n1": item("n1", source="a"), "n2": item("n2", source="b"), "n3": item("n3", "c")}
    vectors = {"n1": BASE, "n2": vec(0.99), "n3": vec(0.5)}
    pairs = mark_near_duplicates(store, ["n1", "n2", "n3"], vectors, {})
    assert pairs == [("n2", "n1")]
    assert store["n3"].visible


def test_items_without_vectors_are_skipped() -> None:
    store = {"old": item("old"), "new": item("new", source="b")}
    assert mark_near_duplicates(store, ["new"], {"new": BASE}, {}) == []
    assert mark_near_duplicates(store, ["new"], {"old": BASE}, {}) == []


def test_zero_vector_does_not_crash() -> None:
    store = {"old": item("old"), "new": item("new", source="b")}
    zero = np.zeros(2)
    assert mark_near_duplicates(store, ["new"], {"old": zero, "new": BASE}, {}) == []
