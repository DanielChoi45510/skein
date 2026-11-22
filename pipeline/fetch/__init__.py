"""Source fetchers. `fetch_source` dispatches on `Source.type`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..config.schema import Source
from ..models import RawEntry
from . import reddit, rss
from .http import FetchError, HttpFetcher
from .rss import FeedParseError

__all__ = ["FeedParseError", "FetchError", "FetchOutcome", "HttpFetcher", "fetch_source"]


@dataclass(frozen=True)
class FetchOutcome:
    status: Literal["ok", "unchanged"]
    entries: list[RawEntry] = field(default_factory=list)
    feed_title: str | None = None


def fetch_source(source: Source, http: HttpFetcher) -> FetchOutcome:
    """Fetch and parse one source. Raises FetchError / FeedParseError on failure."""
    if source.type == "rss":
        assert source.url is not None  # guaranteed by the schema
        result = http.get(str(source.url), accept=rss.ACCEPT)
        if result.status == "unchanged":
            return FetchOutcome("unchanged")
        title, entries = rss.parse_feed(source.id, result.content)
        return FetchOutcome("ok", entries, title)

    if source.type == "reddit":
        assert source.subreddit is not None  # guaranteed by the schema
        result = http.get(reddit.listing_url(source.subreddit), accept=reddit.ACCEPT)
        if result.status == "unchanged":
            return FetchOutcome("unchanged")
        entries = reddit.parse_listing(source.id, result.content, source.options)
        return FetchOutcome("ok", entries, f"r/{source.subreddit}")

    raise ValueError(f"unsupported source type: {source.type}")
