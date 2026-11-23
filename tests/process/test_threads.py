"""Thread assignment core (DESIGN §6.5), on hand-made unit vectors."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from pipeline.config import load_config
from pipeline.config.schema import SourceRelevance
from pipeline.models import Item, Thread
from pipeline.process.embed import HashingEmbedder
from pipeline.process.threads import (
    DEFAULT,
    PENDING_WINDOW,
    AskLLM,
    Attach,
    Candidate,
    New,
    Scored,
    Thresholds,
    decide,
    entities,
    entity_boost,
    in_rescue_band,
    is_candidate,
    new_thread_id,
    predefined_anchors,
    predefined_thread_id,
    rank,
    rescue,
    resolve_without_llm,
    route_predefined,
    thread_kind,
    update_centroid,
)

from ..conftest import FIXTURE_CONFIG

NOW = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.UTC)
CFG = load_config(FIXTURE_CONFIG)
NO_BOOST = Thresholds(entity_boost=0.0)


def unit(*xs: float) -> np.ndarray:
    v = np.array(xs, np.float32)
    return v / np.linalg.norm(v)


def at_cos(c: float) -> np.ndarray:
    """A unit vector whose cosine with (1, 0) is exactly c."""
    return np.array([c, np.sqrt(1 - c * c)], np.float32)


E0 = unit(1, 0)


def cand(thread_id: str, centroid: np.ndarray, state: str = "active", ents=()) -> Candidate:
    return Candidate(thread_id, centroid, frozenset(ents), state)


def scored(*scores: float) -> list[Scored]:
    return [Scored(f"t{i}", s, s) for i, s in enumerate(scores)]


# ───────────────────────────── ids ─────────────────────────────


def test_thread_ids_are_deterministic() -> None:
    a = new_thread_id("world", "abc123")
    assert a == new_thread_id("world", "abc123")
    assert a != new_thread_id("politics", "abc123")
    assert a.startswith("t") and len(a) == 13
    assert predefined_thread_id("markets", "energy") == "markets--energy"


def test_thread_kind_per_mode() -> None:
    assert [thread_kind(m) for m in ("threaded", "question", "tracker", "fixed")] == [
        "story",
        "question",
        "tracker",
        "fixed",
    ]
    with pytest.raises(KeyError):
        thread_kind("flat")


# ───────────────────────────── entities ─────────────────────────────


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("OpenAI releases GPT-5 with new benchmarks", {"openai", "gpt-5"}),
        ("Apple unveils the iPhone 18", {"iphone"}),  # plain first word is missed
        ("Germany's coalition talks collapse as SPD walks out", {"spd"}),
        ("Talks in Berlin stall over NATO spending", {"berlin", "nato"}),
        ("Apple Says New M5 MacBook Pro Is Faster", {"m5", "macbook", "pro", "faster"}),
        ("why the Fed held rates", {"fed"}),
        (
            "[AINews] Gemini 4 Neon: GDM's contender",
            {"neon", "gdm"},
        ),  # tag dropped; "Gemini" now leads
    ],
)
def test_entities(title: str, expected: set[str]) -> None:
    assert entities(title) == expected


def test_entity_boost_is_capped() -> None:
    t = Thresholds(entity_boost=0.02, entity_boost_max=0.05)
    a = frozenset({"nato", "berlin", "spd", "merz"})
    assert entity_boost(a, frozenset({"nato"}), t) == pytest.approx(0.02)
    assert entity_boost(a, a, t) == pytest.approx(0.05)
    assert entity_boost(a, frozenset(), t) == 0.0


# ───────────────────────────── ranking ─────────────────────────────


def test_rank_by_cosine_plus_boost() -> None:
    cands = [
        cand("far", at_cos(0.60)),
        cand("near", at_cos(0.70)),
        cand("named", at_cos(0.66), ents={"nato", "berlin"}),
    ]
    ranked = rank(E0, frozenset({"nato", "berlin"}), cands, Thresholds(entity_boost=0.03))
    assert [s.thread_id for s in ranked] == ["named", "near", "far"]
    assert ranked[0].similarity == pytest.approx(0.66, abs=1e-6)
    assert ranked[0].score == pytest.approx(0.72, abs=1e-6)


def test_rank_ties_break_by_thread_id() -> None:
    ranked = rank(E0, frozenset(), [cand("b", at_cos(0.7)), cand("a", at_cos(0.7))], NO_BOOST)
    assert [s.thread_id for s in ranked] == ["a", "b"]


# ───────────────────────────── decisions ─────────────────────────────


def test_no_candidates_means_new() -> None:
    assert decide([]) == New()


H, L, F, M = DEFAULT.high, DEFAULT.low, DEFAULT.fallback, DEFAULT.margin


def test_tuned_thresholds_are_ordered() -> None:
    assert L <= F <= H


def test_high_with_clear_margin_attaches() -> None:
    assert decide(scored(H + 0.05, H + 0.05 - M)) == Attach("t0", H + 0.05)
    assert decide(scored(H)) == Attach("t0", H)


def test_high_without_margin_is_gray_zone() -> None:
    d = decide(scored(H + 0.05, H + 0.04, L, L - 0.1))
    assert isinstance(d, AskLLM)
    assert [o.thread_id for o in d.options] == ["t0", "t1", "t2"]  # top 3 only


def test_between_low_and_high_is_gray_zone() -> None:
    assert isinstance(decide(scored((L + H) / 2)), AskLLM)
    assert isinstance(decide(scored(L)), AskLLM)


def test_below_low_is_new() -> None:
    assert decide(scored(L - 0.01, L - 0.05)) == New()


@pytest.mark.parametrize(
    ("top", "expected"),
    [
        (H + 0.05, Attach("t0", H + 0.05)),  # high but no margin
        (F, Attach("t0", F)),
        (F - 0.01, New()),
        (L, New()),
    ],
)
def test_gray_zone_without_llm_attaches_at_fallback(top: float, expected) -> None:
    d = decide(scored(top, top - 0.01))
    assert isinstance(d, AskLLM)
    assert resolve_without_llm(d) == expected


def test_resolve_passes_clear_decisions_through() -> None:
    assert resolve_without_llm(Attach("x", 0.9)) == Attach("x", 0.9)
    assert resolve_without_llm(New()) == New()


# ───────────────────────────── candidates ─────────────────────────────


def thread(state: str, created_hours_ago: float = 1) -> Thread:
    created = NOW - dt.timedelta(hours=created_hours_ago)
    return Thread(
        id="t1",
        topic_id="world",
        kind="story",
        title="x",
        state=state,
        created_at=created,
        last_item_at=created,
        item_ids=["a"],
    )


@pytest.mark.parametrize("state", ["active", "cooling", "dormant"])
def test_live_threads_are_candidates(state: str) -> None:
    assert is_candidate(thread(state, created_hours_ago=24 * 90), True, NOW)


def test_archived_threads_are_never_candidates() -> None:
    assert not is_candidate(thread("archived"), True, NOW)


def test_pending_threads_are_candidates_for_72_hours() -> None:
    hours = PENDING_WINDOW.total_seconds() / 3600
    assert is_candidate(thread("pending", created_hours_ago=hours), True, NOW)
    assert not is_candidate(thread("pending", created_hours_ago=hours + 0.1), True, NOW)


def test_threads_without_centroid_are_not_candidates() -> None:
    assert not is_candidate(thread("active"), False, NOW)


# ───────────────────────────── rescue ─────────────────────────────


def test_rescue_attaches_to_active_thread_at_high() -> None:
    ranked = scored(H, H - 0.01)  # no margin needed for rescue
    assert rescue(ranked, {"t0": "active"}) == Attach("t0", H)


@pytest.mark.parametrize("state", ["pending", "cooling", "dormant"])
def test_rescue_needs_an_active_thread(state: str) -> None:
    assert rescue(scored(0.90), {"t0": state}) is None


def test_rescue_needs_high_score() -> None:
    assert rescue(scored(H - 0.01), {"t0": "active"}) is None
    assert rescue([], {}) is None


def test_rescue_uses_best_match_only() -> None:
    # Best match is pending; a slightly worse active thread doesn't rescue it.
    assert rescue(scored(H + 0.05, H + 0.01), {"t0": "pending", "t1": "active"}) is None


def item(relevance: float | None, source: str = "example-world", **kw) -> Item:
    fields = {
        "id": "i1",
        "source_id": source,
        "url": "https://example.com/x",
        "canonical_url": "https://example.com/x",
        "title": "x",
        "published_at": NOW,
        "first_seen_at": NOW,
        "topic_id": "world",
        "relevance": relevance,
    }
    return Item(**(fields | kw))


SOURCES = {s.id: s for s in CFG.sources.sources}  # fixture default threshold: 0.30


@pytest.mark.parametrize(
    ("relevance", "expected"),
    [(0.30, False), (0.29, True), (0.25, True), (0.249, False), (None, False)],
)
def test_rescue_band(relevance: float | None, expected: bool) -> None:
    assert in_rescue_band(item(relevance), SOURCES, CFG.topics) is expected


def test_rescue_band_uses_the_most_lenient_carrying_source() -> None:
    strict = SOURCES | {
        "example-world": SOURCES["example-world"].model_copy(
            update={"relevance": SourceRelevance(threshold=0.60)}
        )
    }
    lone = item(0.27)
    covered = item(0.27, also_covered_by=["example-hn"])  # example-hn: default 0.30
    assert not in_rescue_band(lone, strict, CFG.topics)
    assert in_rescue_band(covered, strict, CFG.topics)


# ───────────────────────────── centroids ─────────────────────────────


def test_first_item_is_the_centroid() -> None:
    v = unit(3, 4)
    np.testing.assert_allclose(update_centroid(None, v, 1), v)


def test_young_thread_centroid_is_the_mean() -> None:
    c = update_centroid(unit(1, 0), unit(0, 1), 2)
    np.testing.assert_allclose(c, unit(1, 1), atol=1e-6)


def test_older_thread_weights_newest_item_at_least_min_alpha() -> None:
    c = unit(1, 0)
    v = unit(0, 1)
    after = update_centroid(c, v, 20)  # 1/20 < 0.25: alpha stays 0.25
    np.testing.assert_allclose(after, unit(0.75, 0.25), atol=1e-6)
    assert after.dtype == np.float32
    assert np.linalg.norm(after) == pytest.approx(1.0, abs=1e-6)


# ───────────────────────────── tracker and fixed ─────────────────────────────


def test_predefined_anchors_cover_tracker_and_fixed_topics_only() -> None:
    anchors = predefined_anchors(CFG.topics.topics, HashingEmbedder())
    assert list(anchors) == [
        "trackers--phones",
        "trackers--laptops",
        "markets--energy",
        "markets--rates",
    ]


def test_route_predefined_picks_nearest_anchor() -> None:
    anchors = {"m--energy": unit(1, 0), "m--rates": unit(0, 1)}
    assert route_predefined(unit(0.2, 0.9), anchors).thread_id == "m--rates"
    # Ties go to the thread listed first.
    assert route_predefined(unit(1, 1), anchors).thread_id == "m--energy"


def test_route_predefined_always_attaches() -> None:
    anchors = {"m--energy": unit(1, 0)}
    assert route_predefined(unit(-1, 0.01), anchors).thread_id == "m--energy"
    with pytest.raises(ValueError):
        route_predefined(unit(1, 0), {})


class RecordingEmbedder(HashingEmbedder):
    def __init__(self) -> None:
        super().__init__()
        self.texts: list[str] = []

    def embed(self, texts, kind):  # type: ignore[override]
        self.texts += list(texts)
        return super().embed(texts, kind)


def test_predefined_anchor_uses_description_else_title() -> None:
    trackers = next(t for t in CFG.topics.topics if t.id == "trackers")
    assert trackers.threads is not None
    phones, laptops = trackers.threads
    described = trackers.model_copy(
        update={
            "threads": [phones.model_copy(update={"description": "Smartphones: iPhone"}), laptops]
        }
    )
    embedder = RecordingEmbedder()
    predefined_anchors([described], embedder)
    assert embedder.texts == ["Smartphones: iPhone", "Laptops"]
