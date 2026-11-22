"""Data models passed between pipeline stages and stored in the state dir."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class RawEntry(BaseModel):
    """One entry as a fetcher returns it, before normalization (step b).

    `summary` is the feed's own description (HTML for RSS/Atom, plain text for
    Reddit). It is never full article text and gets truncated during normalization.
    """

    model_config = ConfigDict(frozen=True)

    source_id: str
    url: str
    title: str
    summary: str | None = None
    published: dt.datetime | None = None  # UTC, when the feed provides one
    extra: dict[str, Any] = {}


HiddenReason = Literal["duplicate", "below_threshold"]


class Item(BaseModel):
    """One stored item (DESIGN §3.1). Metadata and a link only, never full text.

    Stored as NDJSON in `items/YYYY-MM-DD.ndjson`, partitioned by `first_seen_at`.
    """

    id: str  # first 16 hex chars of sha256(canonical_url)
    source_id: str
    url: str
    canonical_url: str
    title: str
    excerpt: str | None = None  # feed-provided, plain text, ≤ 300 chars
    published_at: dt.datetime
    first_seen_at: dt.datetime
    also_covered_by: list[str] = []  # other sources that carried the same story
    duplicate_of: str | None = None  # id of the item kept instead of this one
    hidden_reason: HiddenReason | None = None
    topic_id: str | None = None  # set by relevance (step c)
    relevance: float | None = None  # step c
    importance: float | None = None  # step c
    extra: dict[str, Any] = {}  # small source metadata, e.g. Reddit score / flair

    @property
    def visible(self) -> bool:
        return self.hidden_reason is None


FetchStatus = Literal["ok", "unchanged", "error"]


class SourceHealth(BaseModel):
    """Per-source fetch health, stored in `source_health.json` (DESIGN §9.4)."""

    last_attempt_at: dt.datetime | None = None
    last_status: FetchStatus | None = None
    last_success_at: dt.datetime | None = None
    last_item_count: int | None = None
    last_error: str | None = None
    last_error_at: dt.datetime | None = None
    consecutive_failures: int = 0
    feed_title: str | None = None  # the feed's own title, for display names later


class CacheEntry(BaseModel):
    """Validators for conditional GET, stored in `http_cache.json`."""

    etag: str | None = None
    last_modified: str | None = None
