"""RSS / Atom sources."""

from __future__ import annotations

import datetime as dt
import time

import feedparser

from ..models import RawEntry
from .images import entry_image

ACCEPT = "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8"


class FeedParseError(Exception):
    pass


def parse_feed(source_id: str, content: bytes) -> tuple[str | None, list[RawEntry]]:
    """Parse feed bytes into (feed title, entries). Never lets feedparser touch the network."""
    parsed = feedparser.parse(content)
    # An HTML error page parses "cleanly" with no entries and no detected feed format.
    if not parsed.entries and (parsed.bozo or not parsed.get("version")):
        exc = parsed.get("bozo_exception")
        reason = type(exc).__name__ if exc else "unrecognized format"
        raise FeedParseError(f"not a valid RSS/Atom feed ({reason})")

    entries = []
    for e in parsed.entries:
        url = (e.get("link") or "").strip()
        title = (e.get("title") or "").strip()
        if not url or not title:
            continue
        extra = {}
        if comments := e.get("comments"):
            extra["comments_url"] = comments
        entries.append(
            RawEntry(
                source_id=source_id,
                url=url,
                title=title,
                summary=e.get("summary") or None,
                published=_to_utc(e.get("published_parsed") or e.get("updated_parsed")),
                image_url=entry_image(e),
                extra=extra,
            )
        )
    title = (parsed.feed.get("title") or "").strip() or None
    return title, entries


def _to_utc(t: time.struct_time | None) -> dt.datetime | None:
    # feedparser normalizes *_parsed values to UTC.
    if t is None:
        return None
    return dt.datetime(*t[:6], tzinfo=dt.UTC)
