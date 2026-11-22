"""The static JSON the site reads (DESIGN §6.8). This is the frontend's contract.

    feed/index.json         FeedIndex
    feed/topics/<id>.json   TopicFeed

Bump SCHEMA_VERSION on any breaking change, and update web/src/lib/types.ts.
Only public fields belong here: no full text, nothing from the private profile.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


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


class TopicFeed(_Out):
    schema_version: int = SCHEMA_VERSION
    id: str
    name: str
    group: str
    mode: str
    days: list[Day]  # newest first


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
