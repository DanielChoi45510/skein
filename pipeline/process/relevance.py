"""Topic relevance (DESIGN §6.4).

Each topic's `description` and `include` examples are positive anchors; its
`exclude` examples are negative anchors. For an item and a topic:

    relevance = max cos(item, positives) - λ * max cos(item, negatives), clipped to [0, 1]

An item is scored against every topic its source feeds and goes to the best one.
Below the threshold it's hidden (`below_threshold`) but keeps its best topic and
score, for calibration now and the Hidden screen later.

Threshold precedence: source `relevance.threshold` → topic `relevance_threshold`
→ `defaults.relevance_threshold`. A source with `relevance: {skip: true}` routes
straight to its single topic with relevance 1.0.
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
    value = float(np.max(anchors.positive @ vector))
    if anchors.negative is not None:
        value -= NEGATIVE_WEIGHT * float(np.max(anchors.negative @ vector))
    return min(1.0, max(0.0, value))


def threshold_for(source: Source, topic: Topic, topics: TopicsFile) -> float:
    if source.relevance and source.relevance.threshold is not None:
        return source.relevance.threshold
    if topic.relevance_threshold is not None:
        return topic.relevance_threshold
    return topics.defaults.relevance_threshold


def assign_topics(
    items: list[Item],
    sources: Mapping[str, Source],
    topics: TopicsFile,
    embedder: Embedder,
) -> None:
    """Set topic_id and relevance on each item; hide those below their threshold."""
    by_id = {t.id: t for t in topics.topics}
    to_score: list[Item] = []
    for item in items:
        source = sources[item.source_id]
        if source.relevance and source.relevance.skip:
            item.topic_id, item.relevance = source.topics[0], 1.0
        else:
            to_score.append(item)
    if not to_score:
        return

    needed = {tid for i in to_score for tid in sources[i.source_id].topics if tid in by_id}
    anchors = build_anchors((by_id[t] for t in sorted(needed)), embedder)
    vectors = embedder.embed([item_text(i) for i in to_score], "passage")
    for item, vector in zip(to_score, vectors, strict=True):
        source = sources[item.source_id]
        # Ties go to the topic listed first on the source.
        scored = [(score(vector, anchors[t]), t) for t in source.topics if t in anchors]
        best_score, best_topic = max(scored, key=lambda st: st[0])
        item.topic_id = best_topic
        item.relevance = round(best_score, 4)
        if best_score < threshold_for(source, by_id[best_topic], topics):
            item.hidden_reason = "below_threshold"
