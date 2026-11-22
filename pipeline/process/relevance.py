"""Topic relevance (DESIGN §6.4).

Each topic's `description` and `include` examples are positive anchors; its
`exclude` examples are negative anchors. For an item and a topic:

    pos = max cos(item, positives),  neg = max cos(item, negatives)
    relevance = pos - λ * max(0, neg - pos), clipped to [0, 1]

An exclude only counts against an item that is closer to it than to the topic.
(Subtracting λ·neg outright penalized every item in topics whose excludes are
in-domain, e.g. "Campaign gossip" under US politics: calibration showed a flat
~0.27 drop across the whole topic.)

An item is scored against every topic its source feeds and goes to the best one.
Only the score is stored. Thresholds are applied at export (`passes_threshold`),
so changing one takes effect on the next run, for stored items too.

Threshold precedence: source `relevance.threshold` → topic `relevance_threshold`
→ `defaults.relevance_threshold`. A source with `relevance: {skip: true}` is never
hidden by a threshold; its items are still scored, so ranking uses real relevance.
An item shows if any source that carried it (its own or `also_covered_by`) would
show it: a story an NYT section feed carried isn't hidden because HN's copy
scored low.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np

from ..config.schema import Source, Topic, TopicsFile
from ..models import Item
from .embed import Embedder

NEGATIVE_WEIGHT = 0.5  # λ


@dataclass(frozen=True)
class Anchors:
    positive: np.ndarray  # (p, d)
    negative: np.ndarray | None  # (n, d), None when the topic has no `exclude`


def anchor_texts(topic: Topic) -> tuple[list[str], list[str]]:
    return [topic.description, *topic.include], list(topic.exclude)


def build_anchors(topics: Iterable[Topic], embedder: Embedder) -> dict[str, Anchors]:
    """Embed every topic's anchors in one batch."""
    topics = list(topics)
    texts: list[str] = []
    spans: list[tuple[str, int, int, int]] = []
    for t in topics:
        pos, neg = anchor_texts(t)
        start = len(texts)
        texts += pos + neg
        spans.append((t.id, start, start + len(pos), start + len(pos) + len(neg)))
    vectors = embedder.embed(texts, "query") if texts else None
    out = {}
    for topic_id, start, mid, end in spans:
        assert vectors is not None
        out[topic_id] = Anchors(vectors[start:mid], vectors[mid:end] if end > mid else None)
    return out


def item_text(item: Item) -> str:
    return f"{item.title}. {item.excerpt}" if item.excerpt else item.title


def score(vector: np.ndarray, anchors: Anchors) -> float:
    pos = float(np.max(anchors.positive @ vector))
    value = pos
    if anchors.negative is not None:
        neg = float(np.max(anchors.negative @ vector))
        value -= NEGATIVE_WEIGHT * max(0.0, neg - pos)
    return min(1.0, max(0.0, value))


def threshold_for(source: Source, topic: Topic, topics: TopicsFile) -> float:
    if source.relevance and source.relevance.threshold is not None:
        return source.relevance.threshold
    if topic.relevance_threshold is not None:
        return topic.relevance_threshold
    return topics.defaults.relevance_threshold


def passes_threshold(item: Item, sources: Mapping[str, Source], topics: TopicsFile) -> bool:
    """Whether any source that carried the item would show it in the item's topic."""
    topic = next((t for t in topics.topics if t.id == item.topic_id), None)
    if topic is None:
        return False
    for source_id in (item.source_id, *item.also_covered_by):
        source = sources.get(source_id)
        if source is None:
            continue
        if source.relevance and source.relevance.skip:
            return True
        if item.relevance is not None and item.relevance >= threshold_for(source, topic, topics):
            return True
    return False


def assign_topics(
    items: list[Item],
    sources: Mapping[str, Source],
    topics: TopicsFile,
    embedder: Embedder,
) -> None:
    """Set topic_id (best-scoring topic of the item's source) and relevance on each item."""
    if not items:
        return
    by_id = {t.id: t for t in topics.topics}
    needed = {tid for i in items for tid in sources[i.source_id].topics if tid in by_id}
    anchors = build_anchors((by_id[t] for t in sorted(needed)), embedder)
    vectors = embedder.embed([item_text(i) for i in items], "passage")
    for item, vector in zip(items, vectors, strict=True):
        source = sources[item.source_id]
        # Ties go to the topic listed first on the source.
        scored = [(score(vector, anchors[t]), t) for t in source.topics if t in anchors]
        best_score, best_topic = max(scored, key=lambda st: st[0])
        item.topic_id = best_topic
        item.relevance = round(best_score, 4)
