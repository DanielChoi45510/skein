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
