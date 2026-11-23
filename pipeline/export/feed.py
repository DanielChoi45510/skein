"""Write the static feed JSON (DESIGN §6.6 caps, §6.8 files).

Phase 1 shows every topic as a flat ranked list (threads arrive in Phase 2):
- items within the topic's lookback window, grouped by UTC day of publication;
- ranked by importance (computed here; it depends on the current time);
- caps: `max_per_day` per day; `max_per_week` / `target_per_week` over the
  trailing 7 days and `max_per_month` over the trailing 30 days; a topic with
  none of these uses `defaults.daily_cap_per_thread` per day. Items over a cap
  are exported with `collapsed: true` ("+N more"), never dropped.
Relevance thresholds are applied here, from stored scores, so a threshold change
takes effect on the next run (see process/relevance.py). Only enabled sources
count, so disabling a source hides its stored items on the next run too.
Duplicates, items below every carrying source's threshold, items whose title
every carrying source excludes (`title_exclude`), and items carried only by
disabled or removed sources are never exported. Titles are cleaned on the way
out (`clean_title`), so items stored before the cleanup display the same.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Iterable, Mapping
from pathlib import Path

from ..config.schema import Topic, TopicsFile
from ..config.validate import Config
from ..models import Item, SourceHealth
from ..process.normalize import clean_title, excluded_by_title
from ..process.rank import importance
from ..process.relevance import passes_threshold
from ..state import write_text_atomic
from .models import (
    Day,
    ExportItem,
    FeedIndex,
    GroupSummary,
    SourceSummary,
    TopicFeed,
    TopicSummary,
)

log = logging.getLogger(__name__)

FEED_DIR = "feed"
TOPICS_DIR = "topics"
_WINDOW_CAPS = (("max_per_week", 7), ("target_per_week", 7), ("max_per_month", 30))


def export_feed(
    out_dir: Path,
    cfg: Config,
    items: Iterable[Item],
    health: Mapping[str, SourceHealth],
    now: dt.datetime,
) -> FeedIndex:
    """Write feed/index.json and feed/topics/<id>.json; remove stale topic files."""
    # Only enabled sources count: disabling (or removing) a source hides its stored
    # items on the next run. A story it shared with an enabled source stays, because
    # an item shows if any enabled source that carried it would show it.
    enabled = {s.id: s for s in cfg.sources.sources if s.status != "disabled"}
    weights = {s.id: s.weight for s in cfg.sources.sources}
    enabled_topics = {t for s in enabled.values() for t in s.topics}
    by_topic: dict[str, list[Item]] = {}
    below = no_source = excluded = 0
    for item in items:
        if not item.visible or item.topic_id is None:
            continue
        if not any(sid in enabled for sid in (item.source_id, *item.also_covered_by)):
            no_source += 1
        elif excluded_by_title(item, enabled):
            excluded += 1
        elif passes_threshold(item, enabled, cfg.topics):
            by_topic.setdefault(item.topic_id, []).append(item)
        else:
            below += 1
    log.info("%d stored item(s) below their relevance threshold, not exported", below)
    if excluded:
        log.info("%d stored item(s) match their sources' title_exclude, not exported", excluded)
    if no_source:
        log.info("%d stored item(s) only from disabled or removed sources, not exported", no_source)

    feeds = {
        t.id: build_topic_feed(t, by_topic.get(t.id, []), cfg.topics, weights, now)
        for t in cfg.topics.topics
    }
    index = FeedIndex(
        generated_at=now,
        groups=[
            GroupSummary(
                id=g.id,
                name=g.name,
                topics=[
                    _summary(t, feeds[t.id], t.id in enabled_topics)
                    for t in cfg.topics.topics
                    if t.group == g.id
                ],
            )
            for g in cfg.topics.groups
        ],
        sources=[
            SourceSummary(
                id=s.id,
                name=s.name or (health[s.id].feed_title if s.id in health else None) or s.id,
                type=s.type,
                status=s.status,
                lean=s.lean,
                kind=s.kind,
                paywall=s.paywall,
            )
            for s in cfg.sources.sources
        ],
    )

    feed_dir = out_dir / FEED_DIR
    topics_dir = feed_dir / TOPICS_DIR
    for topic_id, feed in feeds.items():
        write_text_atomic(topics_dir / f"{topic_id}.json", feed.model_dump_json() + "\n")
    for stale in topics_dir.glob("*.json"):
        if stale.stem not in feeds:
            stale.unlink()
    write_text_atomic(feed_dir / "index.json", index.model_dump_json() + "\n")
    return index


def build_topic_feed(
    topic: Topic,
    items: list[Item],
    topics: TopicsFile,
    weights: Mapping[str, float],
    now: dt.datetime,
) -> TopicFeed:
    lookback = topic.lookback_days or topics.defaults.lookback_days
    oldest = now - dt.timedelta(days=lookback)
    scored = [
        (item, importance(item, weights.get(item.source_id, 1.0), now))
        for item in items
        if item.published_at >= oldest
    ]
    # Rank: importance, then newest, then id (stable output).
    scored.sort(key=lambda p: (-p[1], -p[0].published_at.timestamp(), p[0].id))
    collapsed = _collapsed_ids(topic, topics, scored, now)

    days: dict[dt.date, list[ExportItem]] = {}
    for item, imp in scored:
        days.setdefault(item.published_at.astimezone(dt.UTC).date(), []).append(
            ExportItem(
                id=item.id,
                title=clean_title(item.title),
                url=item.url,
                source_id=item.source_id,
                published_at=item.published_at,
                first_seen_at=item.first_seen_at,
                excerpt=item.excerpt,
                importance=round(imp, 4),
                also_covered_by=item.also_covered_by,
                collapsed=item.id in collapsed,
            )
        )
    return TopicFeed(
        id=topic.id,
        name=topic.name,
        group=topic.group,
        mode=topic.mode,
        days=[
            # Stable sort keeps importance order within visible and within collapsed.
            Day(date=d, items=sorted(days[d], key=lambda i: i.collapsed))
            for d in sorted(days, reverse=True)
        ],
    )


def _collapsed_ids(
    topic: Topic, topics: TopicsFile, ranked: list[tuple[Item, float]], now: dt.datetime
) -> set[str]:
    """Ids of items over a cap. `ranked` is in importance order."""
    collapsed: set[str] = set()
    has_window_cap = any(getattr(topic, field) for field, _ in _WINDOW_CAPS)
    daily_cap = topic.max_per_day or (
        None if has_window_cap else topics.defaults.daily_cap_per_thread
    )
    if daily_cap:
        per_day: dict[dt.date, int] = {}
        for item, _ in ranked:
            day = item.published_at.astimezone(dt.UTC).date()
            per_day[day] = per_day.get(day, 0) + 1
            if per_day[day] > daily_cap:
                collapsed.add(item.id)
    for field, days in _WINDOW_CAPS:
        cap = getattr(topic, field)
        if not cap:
            continue
        since = now - dt.timedelta(days=days)
        shown = 0
        for item, _ in ranked:
            if item.id in collapsed or item.published_at < since:
                continue
            shown += 1
            if shown > cap:
                collapsed.add(item.id)
    return collapsed


def _summary(topic: Topic, feed: TopicFeed, has_sources: bool) -> TopicSummary:
    items = [i for d in feed.days for i in d.items]
    return TopicSummary(
        id=topic.id,
        name=topic.name,
        mode=topic.mode,
        has_sources=has_sources,
        visible_count=sum(1 for i in items if not i.collapsed),
        collapsed_count=sum(1 for i in items if i.collapsed),
        latest_first_seen_at=max((i.first_seen_at for i in items), default=None),
    )
