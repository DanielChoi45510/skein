"""The static JSON the site reads (DESIGN §6.8). This is the frontend's contract.

    feed/index.json          FeedIndex
    feed/topics/<id>.json    TopicFeed (threads summarized, loose items by day)
    feed/threads/<id>.json   ThreadFeed (one thread's items by day)

Bump SCHEMA_VERSION on any breaking change, and update web/src/lib/types.ts.
Only public fields belong here: no full text, nothing from the private profile.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 2  # 2: threads (Phase 2a)


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExportItem(_Out):
    id: str
    title: str
    url: str
    source_id: str
    published_at: dt.datetime
    first_seen_at: dt.datetime
    excerpt: str | None = Field(default=None, max_length=300)
    importance: float
    also_covered_by: list[str]
    collapsed: bool  # over the cap: shown behind "+N more", never dropped


class Day(_Out):
    date: dt.date  # UTC day of published_at
    items: list[ExportItem]  # ranked by importance; collapsed items last


class ThreadSummary(_Out):
    """A thread as listed in its topic. Only promoted threads (not pending, not archived)."""

    id: str
    title: str
    kind: str  # story | question | tracker | fixed
    state: str  # active | cooling | dormant
    last_item_at: dt.datetime  # newest exported item's published_at
    item_count: int  # exported items, collapsed included
    collapsed_count: int  # over the per-thread daily cap
    latest_first_seen_at: dt.datetime  # for "N new" hints
    first_seen: list[dt.datetime]  # first_seen_at of every shown (not collapsed) item, newest first
    latest: ExportItem  # the newest item, for a preview line
    pinned: bool = False  # owner override: listed first


class MutedThread(_Out):
    """A thread the owner muted: not listed and its items not exported (DESIGN §10.2)."""

    id: str
    title: str


class TopicFeed(_Out):
    schema_version: int = SCHEMA_VERSION
    id: str
    name: str
    group: str
    mode: str
    threads: list[ThreadSummary]  # pinned first, then newest update; empty for unthreaded modes
    days: list[Day]  # newest first; in threaded modes only items not in a listed thread
    muted: list[MutedThread] = []  # so the owner can unmute; by title


class ThreadFeed(_Out):
    schema_version: int = SCHEMA_VERSION
    id: str
    topic_id: str
    title: str
    kind: str
    state: str
    created_at: dt.datetime
    last_item_at: dt.datetime
    days: list[Day]  # newest first; per-thread daily cap (§6.6), not the topic's lookback


class TopicSummary(_Out):
    id: str
    name: str
    mode: str
    has_sources: bool  # an enabled source feeds this topic
    visible_count: int
    collapsed_count: int
    latest_first_seen_at: dt.datetime | None  # newest item's first_seen_at, for "N new" hints


class GroupSummary(_Out):
    id: str
    name: str
    topics: list[TopicSummary]


class SourceSummary(_Out):
    id: str
    name: str
    type: str
    status: str  # "trial" sources are badged in the UI
    lean: str | None
    kind: str | None
    paywall: str  # none | partial | full


class FeedIndex(_Out):
    schema_version: int = SCHEMA_VERSION
    generated_at: dt.datetime
    groups: list[GroupSummary]
    sources: list[SourceSummary]
