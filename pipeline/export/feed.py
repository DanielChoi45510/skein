"""Write the static feed JSON (DESIGN §6.6 caps, §6.8 files).

Which stored items are exported (all decided here, from stored data and the
current config, so config changes take effect on the next run):
- visible (not a duplicate), routed to a topic, carried by an enabled source;
- not excluded by the title rules of every carrying source (`title_exclude`);
- passing the relevance threshold (process/relevance.py), or **rescued**: within
  RESCUE_BAND below it and attached to a promoted thread with
  `thread_score ≥ T_high` (DESIGN §6.5).

Topic files (`topics/<id>.json`):
- `threads`: the topic's promoted threads (active, cooling, dormant) with at
  least one exported item, newest update first. Not limited to the lookback,
  so dormant threads still list.
- `days`: the other items within the topic's lookback (flat topics: all of
  them; threaded topics: pending single items and unthreaded ones), grouped by
  UTC day of publication, ranked by importance, with the topic's caps:
  `max_per_day` per day; `max_per_week` / `target_per_week` over the trailing 7
  days and `max_per_month` over 30; else `defaults.daily_cap_per_thread` per day.

Thread files (`threads/<id>.json`): every exported item of the thread among the
loaded items (≈ 30 days), by UTC day, ranked by importance, with the per-thread
daily cap (`daily_cap_per_thread`).

Owner overrides (DESIGN §10.2): a renamed thread is exported with its new title;
pinned threads list first (`pinned: true`); muted threads aren't listed, none of
their items are exported, and the topic file names them in `muted` so the owner
can unmute.

Items over a cap are exported with `collapsed: true` ("+N more"), never dropped.
Titles are cleaned and stripped on the way out (`display_title`). Stale topic
and thread files are removed.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Iterable, Mapping
from pathlib import Path

from ..config.schema import Source, Topic, TopicsFile
from ..config.validate import Config
from ..models import Item, SourceHealth, Thread
from ..overrides import EMPTY, Overrides
from ..process.normalize import display_title, excluded_by_title
from ..process.rank import importance
from ..process.relevance import passes_threshold
from ..process.threads import DEFAULT, in_rescue_band
from ..state import write_text_atomic
from .models import (
    Day,
    ExportItem,
    FeedIndex,
    GroupSummary,
    MutedThread,
    SourceSummary,
    ThreadFeed,
    ThreadSummary,
    TopicFeed,
    TopicSummary,
)

log = logging.getLogger(__name__)

FEED_DIR = "feed"
TOPICS_DIR = "topics"
THREADS_DIR = "threads"
LISTED_STATES = frozenset({"active", "cooling", "dormant"})  # promoted and not archived
_WINDOW_CAPS = (("max_per_week", 7), ("target_per_week", 7), ("max_per_month", 30))

Scored = list[tuple[Item, float]]


def export_feed(
    out_dir: Path,
    cfg: Config,
    items: Iterable[Item],
    health: Mapping[str, SourceHealth],
    now: dt.datetime,
    threads: Mapping[str, Thread] | None = None,
    overrides: Overrides = EMPTY,
) -> FeedIndex:
    """Write feed/index.json, feed/topics/<id>.json and feed/threads/<id>.json."""
    threads = threads or {}
    # Only enabled sources count: disabling (or removing) a source hides its stored
    # items on the next run. A story it shared with an enabled source stays, because
    # an item shows if any enabled source that carried it would show it.
    enabled = {s.id: s for s in cfg.sources.sources if s.status != "disabled"}
    weights = {s.id: s.weight for s in cfg.sources.sources}
    all_sources = {s.id: s for s in cfg.sources.sources}  # display rules apply to any source
    enabled_topics = {t for s in enabled.values() for t in s.topics}

    muted = overrides.muted
    by_topic: dict[str, list[Item]] = {}
    below = no_source = excluded = rescued = hidden = 0
    for item in items:
        if not item.visible or item.topic_id is None:
            continue
        if item.thread_id in muted:
            hidden += 1
            continue
        if not any(sid in enabled for sid in (item.source_id, *item.also_covered_by)):
            no_source += 1
        elif excluded_by_title(item, enabled):
            excluded += 1
        elif passes_threshold(item, enabled, cfg.topics):
            by_topic.setdefault(item.topic_id, []).append(item)
        elif _rescued(item, threads, enabled, cfg.topics):
            by_topic.setdefault(item.topic_id, []).append(item)
            rescued += 1
        else:
            below += 1
    log.info("%d stored item(s) below their relevance threshold, not exported", below)
    if hidden:
        log.info("%d item(s) in muted threads, not exported", hidden)
    if rescued:
        log.info("%d item(s) below their threshold kept by an active thread (rescue)", rescued)
    if excluded:
        log.info("%d stored item(s) match their sources' title_exclude, not exported", excluded)
    if no_source:
        log.info("%d stored item(s) only from disabled or removed sources, not exported", no_source)

    feeds: dict[str, TopicFeed] = {}
    thread_feeds: dict[str, ThreadFeed] = {}
    for topic in cfg.topics.topics:
        listed = {
            th.id: th
            for th in threads.values()
            if th.topic_id == topic.id and th.state in LISTED_STATES and th.id not in muted
        }
        loose, grouped = [], {}
        for item in by_topic.get(topic.id, []):
            if item.thread_id in listed:
                grouped.setdefault(item.thread_id, []).append(item)
            else:
                loose.append(item)
        feed = build_topic_feed(topic, loose, cfg.topics, weights, now, sources=all_sources)
        summaries = []
        for thread_id, members in grouped.items():
            thread = listed[thread_id]
            tf = build_thread_feed(
                thread, members, topic, cfg.topics, weights, now, sources=all_sources
            ).model_copy(update={"title": overrides.title(thread_id, thread.title)})
            thread_feeds[thread_id] = tf
            summaries.append(_thread_summary(tf, pinned=thread_id in overrides.pinned))
        summaries.sort(key=lambda s: (not s.pinned, -s.last_item_at.timestamp(), s.id))
        muted_here = sorted(
            (
                MutedThread(id=th.id, title=overrides.title(th.id, th.title))
                for th in threads.values()
                if th.topic_id == topic.id and th.id in muted and th.state != "archived"
            ),
            key=lambda m: (m.title.lower(), m.id),
        )
        feeds[topic.id] = feed.model_copy(update={"threads": summaries, "muted": muted_here})

    index = FeedIndex(
        generated_at=now,
        groups=[
            GroupSummary(
                id=g.id,
                name=g.name,
                topics=[
                    _summary(t, feeds[t.id], thread_feeds, t.id in enabled_topics)
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
    _write_all(feed_dir / TOPICS_DIR, feeds)
    _write_all(feed_dir / THREADS_DIR, thread_feeds)
    write_text_atomic(feed_dir / "index.json", index.model_dump_json() + "\n")
    return index


def _rescued(
    item: Item, threads: Mapping[str, Thread], sources: Mapping[str, Source], topics: TopicsFile
) -> bool:
    """§6.5 thread rescue, from stored data: a near-miss attached to a promoted thread at ≥ T_high.

    Assignment only rescues into active threads; a thread that later cooled keeps
    the items it rescued.
    """
    thread = threads.get(item.thread_id or "")
    return (
        thread is not None
        and thread.state in LISTED_STATES
        and item.thread_score is not None
        and item.thread_score >= DEFAULT.high
        and in_rescue_band(item, sources, topics)
    )


def _write_all(directory: Path, feeds: Mapping[str, TopicFeed | ThreadFeed]) -> None:
    for name, feed in feeds.items():
        write_text_atomic(directory / f"{name}.json", feed.model_dump_json() + "\n")
    for stale in directory.glob("*.json"):
        if stale.stem not in feeds:
            stale.unlink()


def _rank(items: Iterable[Item], weights: Mapping[str, float], now: dt.datetime) -> Scored:
    """Importance order, then newest, then id (stable output)."""
    scored = [(item, importance(item, weights.get(item.source_id, 1.0), now)) for item in items]
    scored.sort(key=lambda p: (-p[1], -p[0].published_at.timestamp(), p[0].id))
    return scored


def _days(scored: Scored, collapsed: set[str], sources: Mapping[str, Source]) -> list[Day]:
    days: dict[dt.date, list[ExportItem]] = {}
    for item, imp in scored:
        days.setdefault(item.published_at.astimezone(dt.UTC).date(), []).append(
            ExportItem(
                id=item.id,
                title=display_title(item, sources),
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
    # Stable sort keeps importance order within visible and within collapsed.
    return [
        Day(date=d, items=sorted(days[d], key=lambda i: i.collapsed))
        for d in sorted(days, reverse=True)
    ]


def build_topic_feed(
    topic: Topic,
    items: list[Item],
    topics: TopicsFile,
    weights: Mapping[str, float],
    now: dt.datetime,
    *,
    sources: Mapping[str, Source] | None = None,
) -> TopicFeed:
    """The topic's loose items (`threads` is filled in by export_feed)."""
    lookback = topic.lookback_days or topics.defaults.lookback_days
    oldest = now - dt.timedelta(days=lookback)
    scored = _rank((i for i in items if i.published_at >= oldest), weights, now)
    collapsed = _collapsed_ids(topic, topics, scored, now)
    return TopicFeed(
        id=topic.id,
        name=topic.name,
        group=topic.group,
        mode=topic.mode,
        threads=[],
        days=_days(scored, collapsed, sources or {}),
    )


def build_thread_feed(
    thread: Thread,
    items: list[Item],
    topic: Topic,
    topics: TopicsFile,
    weights: Mapping[str, float],
    now: dt.datetime,
    *,
    sources: Mapping[str, Source] | None = None,
) -> ThreadFeed:
    scored = _rank(items, weights, now)
    cap = topic.daily_cap_per_thread or topics.defaults.daily_cap_per_thread
    return ThreadFeed(
        id=thread.id,
        topic_id=thread.topic_id,
        title=thread.title,
        kind=thread.kind,
        state=thread.state,
        created_at=thread.created_at,
        last_item_at=max(i.published_at for i in items),
        days=_days(scored, _over_daily_cap(scored, cap), sources or {}),
    )


def _over_daily_cap(ranked: Scored, cap: int) -> set[str]:
    """Ids beyond the first `cap` items of each UTC day. `ranked` is in importance order."""
    collapsed: set[str] = set()
    per_day: dict[dt.date, int] = {}
    for item, _ in ranked:
        day = item.published_at.astimezone(dt.UTC).date()
        per_day[day] = per_day.get(day, 0) + 1
        if per_day[day] > cap:
            collapsed.add(item.id)
    return collapsed


def _collapsed_ids(topic: Topic, topics: TopicsFile, ranked: Scored, now: dt.datetime) -> set[str]:
    """Ids of a topic's loose items over a cap. `ranked` is in importance order."""
    has_window_cap = any(getattr(topic, field) for field, _ in _WINDOW_CAPS)
    daily_cap = topic.max_per_day or (
        None if has_window_cap else topics.defaults.daily_cap_per_thread
    )
    collapsed = _over_daily_cap(ranked, daily_cap) if daily_cap else set()
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


def _thread_summary(feed: ThreadFeed, *, pinned: bool = False) -> ThreadSummary:
    items = [i for d in feed.days for i in d.items]
    latest = max(items, key=lambda i: (i.published_at, i.id))
    shown = sorted((i.first_seen_at for i in items if not i.collapsed), reverse=True)
    return ThreadSummary(
        id=feed.id,
        title=feed.title,
        kind=feed.kind,
        state=feed.state,
        last_item_at=feed.last_item_at,
        item_count=len(items),
        collapsed_count=sum(1 for i in items if i.collapsed),
        latest_first_seen_at=max(i.first_seen_at for i in items),
        first_seen=shown,
        latest=latest,
        pinned=pinned,
    )


def _summary(
    topic: Topic, feed: TopicFeed, thread_feeds: Mapping[str, ThreadFeed], has_sources: bool
) -> TopicSummary:
    items = [i for d in feed.days for i in d.items] + [
        i for s in feed.threads for d in thread_feeds[s.id].days for i in d.items
    ]
    return TopicSummary(
        id=topic.id,
        name=topic.name,
        mode=topic.mode,
        has_sources=has_sources,
        visible_count=sum(1 for i in items if not i.collapsed),
        collapsed_count=sum(1 for i in items if i.collapsed),
        latest_first_seen_at=max((i.first_seen_at for i in items), default=None),
    )
