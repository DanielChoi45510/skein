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


# Thresholds are applied at export, so "below threshold" is never stored.
HiddenReason = Literal["duplicate"]


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
    topic_id: str | None = None  # best-scoring topic, also kept for hidden items
    relevance: float | None = None  # 0-1, set with topic_id (importance is computed at export)
    thread_id: str | None = None  # DESIGN §6.5; set once, by thread assignment
    thread_score: float | None = None  # similarity to the thread when attached (rescue, §6.5)
    extra: dict[str, Any] = {}  # small source metadata, e.g. Reddit score / flair

    @property
    def visible(self) -> bool:
        return self.hidden_reason is None


ThreadKind = Literal["story", "question", "tracker", "fixed"]
ThreadState = Literal["pending", "active", "cooling", "dormant", "archived"]


class Thread(BaseModel):
    """A story thread inside a topic (DESIGN §3.1, §5), stored in `threads.json`.

    Centroids are stored separately (`centroids.npy`, rows named by
    `centroid_ids.json`): only threads that can still be matched have one.
    """

    id: str
    topic_id: str
    kind: ThreadKind
    title: str  # keyword title (§6.5), or the config title for predefined threads
    state: ThreadState
    created_at: dt.datetime
    last_item_at: dt.datetime  # newest published_at among its items
    item_ids: list[str] = []  # in the order they were attached


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
