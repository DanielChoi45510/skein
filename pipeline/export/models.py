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
    # The image the feed itself offers, loaded by the reader's browser from the
    # source (never downloaded or re-hosted). None when absent or not allowed.
    image_url: str | None = None
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


class StructureBranch(_Out):
    """A smaller storyline of the thread, hanging off one spine item (DESIGN §6.9)."""

    id: str  # "b-" + its first item's id: stable while that item leads it
    anchor: str  # the spine item it hangs off (closest in meaning and time)
    items: list[str]  # item ids, oldest first


class RelatedThread(_Out):
    """Another listed thread whose items are similar overall (a spoke)."""

    id: str
    title: str  # as exported (owner renames applied)
    topic_id: str
    similarity: float  # thread-centroid cosine, rounded


class ThreadStructure(_Out):
    """Spine and branches of a thread, over its exported items (heuristic; DESIGN §6.9)."""

    spine: list[str]  # item ids of the main storyline, oldest first
    branches: list[StructureBranch]  # by first item, oldest first
    related: list[RelatedThread]  # most similar first


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
    # Absent when the run couldn't compute it (e.g. no embedding model): show a timeline.
    structure: ThreadStructure | None = None


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
