"""Relevance scoring, topic routing, thresholds, ranking and the hashing embedder."""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence

import numpy as np
import pytest

from pipeline.config import load_config
from pipeline.config.schema import SourceRelevance
from pipeline.models import Item
from pipeline.process.embed import HashingEmbedder
from pipeline.process.rank import FRESHNESS_HALF_LIFE_HOURS, freshness, importance
from pipeline.process.relevance import (
    Anchors,
    assign_topics,
    build_anchors,
    item_text,
    passes_threshold,
    score,
)

from ..conftest import FIXTURE_CONFIG

NOW = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.UTC)
CFG = load_config(FIXTURE_CONFIG)

# Keyword → dimension. Fixture topic anchors land on known axes:
#   world: description + include mention "election" → e0; exclude "Celebrity gossip" → e3
#   politics: "politics" / "legislation" → e1;  gadgets: "accessories" → e2
_AXES = {"election": 0, "politics": 1, "legislation": 1, "accessor": 2, "lamp": 2, "gossip": 3}


class KeywordEmbedder:
    """Vectors built from keyword counts, so expected scores can be computed by hand."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []

    def embed(self, texts: Sequence[str], kind: str) -> np.ndarray:
        self.calls.append((list(texts), kind))
        out = np.zeros((len(texts), 5), np.float32)
        for row, text in enumerate(texts):
            lower = text.lower()
            for word, axis in _AXES.items():
                out[row, axis] += lower.count(word)
            if not out[row].any():
                out[row, 4] = 1.0
        return out / np.linalg.norm(out, axis=1, keepdims=True)


# (2, 0, 0, 3) / sqrt(13): pos ≈ 0.555, neg ≈ 0.832, relevance ≈ 0.416
MIDDLING = "Election election gossip gossip gossip"


def item(title: str, source: str = "example-world", **kw) -> Item:
    fields = {
        "id": title.lower().replace(" ", "-"),
        "source_id": source,
        "url": "https://example.com/x",
        "canonical_url": "https://example.com/x",
        "title": title,
        "published_at": NOW,
        "first_seen_at": NOW,
    }
    return Item(**(fields | kw))


def sources(**overrides: dict) -> dict:
    out = {s.id: s for s in CFG.sources.sources}
    for sid, update in overrides.items():
        out[sid.replace("_", "-")] = out[sid.replace("_", "-")].model_copy(update=update)
    return out


def topics_with(**updates: dict):
    return CFG.topics.model_copy(
        update={
            "topics": [
                t.model_copy(update=updates[t.id]) if t.id in updates else t
                for t in CFG.topics.topics
            ]
        }
    )


# ───────────────────────────── score ─────────────────────────────


def test_negative_counts_only_when_closer_than_positive() -> None:
    anchors = Anchors(positive=np.eye(3)[[0]], negative=np.eye(3)[[1]])
    # closer to the topic than to the exclude: no penalty
    assert score(np.array([0.8, 0.6, 0.0]), anchors) == pytest.approx(0.8)
    # closer to the exclude: pos - 0.5 * (neg - pos)
    assert score(np.array([0.6, 0.8, 0.0]), anchors) == pytest.approx(0.6 - 0.5 * 0.2)


def test_score_takes_best_anchor_and_clips() -> None:
    anchors = Anchors(positive=np.eye(3)[[0, 2]], negative=None)
    assert score(np.array([0.0, 0.0, 1.0]), anchors) == 1.0
    negative_only = Anchors(positive=np.eye(3)[[0]], negative=np.eye(3)[[1]])
    assert score(np.array([0.0, 1.0, 0.0]), negative_only) == 0.0


def test_build_anchors() -> None:
    by_id = {t.id: t for t in CFG.topics.topics}
    emb = KeywordEmbedder()
    anchors = build_anchors([by_id["world"], by_id["politics"]], emb)
    assert anchors["world"].positive.shape == (2, 5)  # description + 1 include
    assert anchors["world"].negative is not None and anchors["world"].negative.shape == (1, 5)
    assert anchors["politics"].negative is None
    assert len(emb.calls) == 1 and emb.calls[0][1] == "query"  # one batch, query side


def test_item_text_uses_excerpt_when_present() -> None:
    assert item_text(item("Title")) == "Title"
    assert item_text(item("Title", excerpt="More.")) == "Title. More."


# ───────────────────────────── assign_topics ─────────────────────────────


def test_relevant_item_routed_and_visible() -> None:
    it = item("Election in Freedonia")
    assign_topics([it], sources(), CFG.topics, KeywordEmbedder())
    assert (it.topic_id, it.relevance, it.visible) == ("world", 1.0, True)


def test_negative_anchor_lowers_score_only_when_closer() -> None:
    plain = item("Election news")
    balanced = item("Election gossip")  # as close to the exclude as to the topic
    mostly_gossip = item("Election gossip gossip")  # closer to the exclude
    assign_topics([plain, balanced, mostly_gossip], sources(), CFG.topics, KeywordEmbedder())
    assert plain.relevance == 1.0
    assert balanced.relevance == pytest.approx(math.sqrt(0.5), abs=1e-4)  # no penalty
    pos, neg = 1 / math.sqrt(5), 2 / math.sqrt(5)
    assert mostly_gossip.relevance == pytest.approx(pos - 0.5 * (neg - pos), abs=1e-4)


def test_scoring_never_hides() -> None:
    it = item("Celebrity gossip roundup")
    assign_topics([it], sources(), CFG.topics, KeywordEmbedder())
    assert (it.topic_id, it.relevance, it.hidden_reason) == ("world", 0.0, None)


def test_multi_topic_source_goes_to_best_topic() -> None:
    it = item("Legislation passes", source="example-hn")  # feeds gadgets + politics
    assign_topics([it], sources(), CFG.topics, KeywordEmbedder())
    assert it.topic_id == "politics"


def test_tie_goes_to_first_listed_topic() -> None:
    it = item("Legislation on desk lamps", source="example-hn")
    assign_topics([it], sources(), CFG.topics, KeywordEmbedder())
    assert it.topic_id == "gadgets"  # listed first on example-hn


def test_skip_source_items_are_still_scored() -> None:
    it = item("Celebrity gossip roundup")
    srcs = sources(example_world={"relevance": SourceRelevance(skip=True)})
    assign_topics([it], srcs, CFG.topics, KeywordEmbedder())
    assert (it.topic_id, it.relevance) == ("world", 0.0)  # real score, used for ranking


# ───────────────────────────── passes_threshold (applied at export) ─────────────────────────────


def scored(title: str, source: str = "example-world", **kw) -> Item:
    it = item(title, source, **kw)
    assign_topics([it], sources(), CFG.topics, KeywordEmbedder())
    return it


def test_middling_item_passes_default_threshold() -> None:
    it = scored(MIDDLING)
    assert it.relevance == pytest.approx(0.416, abs=1e-3)
    assert passes_threshold(it, sources(), CFG.topics)  # default 0.30


def test_low_item_fails_default_threshold() -> None:
    assert not passes_threshold(scored("Celebrity gossip roundup"), sources(), CFG.topics)


def test_topic_threshold_override() -> None:
    it = scored(MIDDLING)
    assert not passes_threshold(it, sources(), topics_with(world={"relevance_threshold": 0.5}))


def test_source_threshold_beats_topic_threshold() -> None:
    it = scored(MIDDLING)
    srcs = sources(example_world={"relevance": SourceRelevance(threshold=0.2)})
    assert passes_threshold(it, srcs, topics_with(world={"relevance_threshold": 0.5}))


def test_skip_source_never_hidden() -> None:
    it = scored("Celebrity gossip roundup")
    srcs = sources(example_world={"relevance": SourceRelevance(skip=True)})
    assert passes_threshold(it, srcs, CFG.topics)


def test_any_carrying_source_can_show_the_item() -> None:
    # HN's copy scored low, but a skip-source carried the same story
    it = scored("Celebrity gossip roundup", source="example-hn", also_covered_by=["example-world"])
    it.topic_id = "politics"
    srcs = sources(example_world={"relevance": SourceRelevance(skip=True)})
    assert not passes_threshold(it, sources(), CFG.topics)
    assert passes_threshold(it, srcs, CFG.topics)


def test_corroborating_source_with_lower_threshold() -> None:
    it = item(
        "x",
        source="example-reddit",
        also_covered_by=["example-world", "gone"],  # "gone": no longer in the config
        topic_id="politics",
        relevance=0.42,
    )
    strict = topics_with(politics={"relevance_threshold": 0.9})
    assert not passes_threshold(it, sources(), strict)
    lenient = sources(example_world={"relevance": SourceRelevance(threshold=0.1)})
    assert passes_threshold(it, lenient, strict)


def test_unknown_topic_or_missing_score_never_passes() -> None:
    assert not passes_threshold(item("x", topic_id="removed", relevance=1.0), sources(), CFG.topics)
    assert not passes_threshold(item("x", topic_id="world"), sources(), CFG.topics)


# ───────────────────────────── rank ─────────────────────────────


def test_freshness_half_life() -> None:
    assert freshness(NOW, NOW) == 1.0
    half = NOW - dt.timedelta(hours=FRESHNESS_HALF_LIFE_HOURS)
    assert freshness(half, NOW) == pytest.approx(0.5)
    assert freshness(NOW + dt.timedelta(hours=1), NOW) == 1.0  # future never > 1


def test_importance_formula() -> None:
    it = item("x", relevance=0.8, also_covered_by=["a", "b"])
    expected = 0.8 * 1.2 * (1 + 0.3 * math.log(3))
    assert importance(it, 1.2, NOW) == pytest.approx(expected)
    old = it.model_copy(update={"published_at": NOW - dt.timedelta(hours=72)})
    assert importance(old, 1.2, NOW) == pytest.approx(expected / 4)


def test_importance_without_relevance_is_zero() -> None:
    assert importance(item("x"), 1.0, NOW) == 0.0


# ───────────────────────────── hashing embedder ─────────────────────────────


def test_hashing_embedder_is_deterministic_and_normalized() -> None:
    emb = HashingEmbedder()
    a = emb.embed(["Election results in Freedonia", "Desk lamp review", ""], "passage")
    b = HashingEmbedder().embed(["Election results in Freedonia", "Desk lamp review", ""], "query")
    assert np.array_equal(a, b)
    assert np.allclose(np.linalg.norm(a[:2], axis=1), 1.0)
    assert not a[2].any()  # empty text → zero vector
    same = emb.embed(["ELECTION results, in Freedonia!"], "passage")[0]
    assert float(same @ a[0]) == pytest.approx(1.0)
