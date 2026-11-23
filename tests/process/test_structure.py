"""Thread structure (pipeline/process/structure.py) on hand-made vectors."""

from __future__ import annotations

import datetime as dt

import numpy as np

from pipeline.config import load_config
from pipeline.config.schema import StructureParams
from pipeline.models import Item, Thread
from pipeline.process.structure import (
    Member,
    centroid,
    related_threads,
    storylines,
    structure,
    thread_structures,
)

from ..conftest import FIXTURE_CONFIG

T0 = dt.datetime(2026, 11, 20, 0, 0, tzinfo=dt.UTC)
P = StructureParams(
    link=0.72,
    link_predefined=0.65,
    min_items=3,
    anchor_day_penalty=0.15,
    related=0.8,
    related_max=5,
)


def unit(*xs: float) -> np.ndarray:
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def member(id: str, hours: float, v: np.ndarray) -> Member:
    return Member(id, T0 + dt.timedelta(hours=hours), v)


A, B, C = unit(1, 0, 0), unit(0, 1, 0), unit(0, 0, 1)


def test_storylines_group_similar_vectors() -> None:
    vs = np.stack([A, unit(1, 0.1, 0), B, unit(0.1, 1, 0), C])
    assert storylines(vs, 0.9) == [[0, 1], [2, 3], [4]]


def test_average_linkage_does_not_chain() -> None:
    # a~b and b~c are close, a and c are not: single linkage would chain all three.
    rad = np.deg2rad
    a = unit(1, 0, 0)
    b = unit(np.cos(rad(43)), np.sin(rad(43)), 0)
    c = unit(np.cos(rad(86)), np.sin(rad(86)), 0)
    sims = [float(a @ b), float(b @ c), float(a @ c)]
    assert sims[0] > 0.7 and sims[1] > 0.7 and sims[2] < 0.1
    assert len(storylines(np.stack([a, b, c]), 0.7)) == 2


def test_spine_is_the_largest_storyline_and_the_rest_branch_off_it() -> None:
    ms = [
        member("s1", 0, A),
        member("s2", 5, unit(1, 0.05, 0)),
        member("s3", 10, unit(1, 0, 0.05)),
        member("b1", 6, B),
        member("b2", 7, unit(0.05, 1, 0)),
    ]
    st = structure(ms, P)
    assert st.spine == ["s1", "s2", "s3"]
    assert [b.items for b in st.branches] == [["b1", "b2"]]


def test_branch_anchors_to_the_spine_item_closest_in_meaning_and_time() -> None:
    # The branch leans towards s3 in meaning, but s3 is days later than it starts.
    ms = [
        member("s1", 0, unit(1, 0.1, 0)),
        member("s2", 1, unit(1, 0.25, 0)),
        member("s3", 24 * 5, unit(1, 0.35, 0)),
        member("b1", 1, B),
    ]
    st = structure(ms, P)
    assert st.branches[0].anchor == "s2"  # one hour away beats slightly closer but 5 days off
    no_time = structure(ms, P.model_copy(update={"anchor_day_penalty": 0.0}))
    assert no_time.branches[0].anchor == "s3"


def test_spine_ties_go_to_the_longer_span_then_the_earlier() -> None:
    ms = [
        member("a1", 0, A),
        member("a2", 1, unit(1, 0.05, 0)),
        member("b1", 2, B),
        member("b2", 50, unit(0.05, 1, 0)),
    ]
    assert structure(ms, P).spine == ["b1", "b2"]  # same size, spans longer


def test_small_threads_and_threads_without_shared_storyline_are_all_spine() -> None:
    two = [member("a", 0, A), member("b", 1, B)]
    assert structure(two, P).spine == ["a", "b"] and not structure(two, P).branches
    scattered = [member("a", 0, A), member("b", 1, B), member("c", 2, C)]
    st = structure(scattered, P)
    assert st.spine == ["a", "b", "c"] and not st.branches


def test_predefined_threads_use_the_looser_link() -> None:
    near = unit(1, 0.75, 0)  # cos with A ≈ 0.8
    ms = [member("a", 0, A), member("b", 1, unit(1, 0.05, 0)), member("c", 2, near)]
    p = P.model_copy(update={"link": 0.95, "link_predefined": 0.7})
    assert len(structure(ms, p).branches) == 1
    assert structure(ms, p, predefined=True).spine == ["a", "b", "c"]


def test_related_threads_threshold_order_cap_and_siblings() -> None:
    cents = {"t1": A, "t2": unit(1, 0.2, 0), "t3": unit(1, 0.4, 0), "t4": B}
    rel = related_threads(cents, P)
    assert [r for r, _ in rel["t1"]] == ["t2", "t3"]
    assert rel["t4"] == []
    assert [
        r for r, _ in related_threads(cents, P.model_copy(update={"related_max": 1}))["t1"]
    ] == ["t2"]
    # Two predefined threads of the same topic are never related.
    siblings = {"t1": "markets", "t2": "markets"}
    assert [r for r, _ in related_threads(cents, P, siblings)["t1"]] == ["t3"]


def test_centroid() -> None:
    c = centroid([A, B])
    assert c is not None and np.isclose(np.linalg.norm(c), 1.0)
    assert centroid([]) is None


def test_thread_structures_skips_pending_muted_and_hidden_items() -> None:
    cfg = load_config(FIXTURE_CONFIG)

    def it(id: str, hours: float, **kw) -> Item:
        when = T0 + dt.timedelta(hours=hours)
        return Item(
            id=id, source_id="example-world", url=f"https://e.com/{id}",
            canonical_url=f"https://e.com/{id}", title=id, published_at=when, first_seen_at=when,
            **kw,
        )  # fmt: skip

    items = {i.id: i for i in [it("a", 0), it("b", 1), it("h", 2, hidden_reason="duplicate")]}
    items |= {"c": it("c", 3), "d": it("d", 4)}

    def thread(id: str, state: str, ids: list[str]) -> Thread:
        return Thread(
            id=id, topic_id="world", kind="story", title=id, state=state,
            created_at=T0, last_item_at=T0, item_ids=ids,
        )  # fmt: skip

    threads = {
        "t1": thread("t1", "active", ["a", "b", "h"]),
        "t2": thread("t2", "pending", ["c"]),
        "t3": thread("t3", "cooling", ["d"]),
    }
    asked: list[list[str]] = []

    def vectors_for(needed: list[Item]) -> dict[str, np.ndarray]:
        asked.append(sorted(i.id for i in needed))
        return {i.id: A for i in needed}

    out = thread_structures(items, threads, cfg.topics, vectors_for, skip={"t3"})
    assert asked == [["a", "b"]]  # one call; no hidden, pending or muted items
    assert set(out.threads) == {"t1"} and out.threads["t1"].spine == ["a", "b"]
