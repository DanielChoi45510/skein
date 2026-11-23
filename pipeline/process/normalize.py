"""Normalize raw entries into Items (DESIGN §6.2).

Canonical URLs (tracking parameters stripped), plain-text excerpts of at most
300 characters, clean titles, UTC dates, the lookback cut, and each source's
`title_exclude` patterns.

Titles arrive decoded (feedparser / Reddit JSON), but some feeds double-encode
markup, so a title can hold literal "<i>…</i>". `clean_title` removes only
inline formatting tags and decodes leftover entities: a literal "<canvas>" in a
headline is text and stays. The export applies it again, so titles stored
before the cleanup display cleanly too.

`title_exclude` (sources.yaml) drops a source's entries whose title matches any
pattern, e.g. stock-quote pages that a search feed returns as if they were
news. Stored items are checked again at export and before threading, so adding
a pattern also hides what the source already delivered.
"""

from __future__ import annotations

import datetime as dt
import functools
import hashlib
import html
import re
from collections.abc import Iterable, Mapping
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..config.schema import Source, TopicsFile
from ..models import Item, RawEntry

EXCERPT_MAX = 300
ELLIPSIS = "…"
FUTURE_TOLERANCE = dt.timedelta(minutes=5)

# Query parameters that only track the click, never select the content.
_TRACKING_PARAMS = frozenset(
    {"fbclid", "gclid", "dclid", "msclkid", "igshid", "smid", "smtyp", "ref", "ref_src", "partner"}
)
_TRACKING_PREFIXES = ("utm_", "mc_")
_DEFAULT_PORTS = {"http": 80, "https": 443}
_WS = re.compile(r"\s+")
# Inline formatting only; anything else in a decoded title is literal text.
_INLINE_TAG = re.compile(
    r"</?(?:a|abbr|b|cite|code|em|font|i|mark|q|s|small|span|strong|sub|sup|u)(?:\s[^<>]*)?/?>",
    re.IGNORECASE,
)


def clean_title(title: str) -> str:
    """Strip inline formatting tags, decode entities, collapse whitespace."""
    return _WS.sub(" ", _INLINE_TAG.sub("", html.unescape(title))).strip()


@functools.cache
def _compiled(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def title_excluded(title: str, source: Source) -> bool:
    """Whether the title matches one of the source's `title_exclude` patterns (case-insensitive)."""
    return any(_compiled(p).search(title) for p in source.title_exclude)


def excluded_by_title(item: Item, sources: Mapping[str, Source]) -> bool:
    """True when every known source that carried the item excludes its title.

    Like thresholds (§6.4): a story another source carried without excluding it
    still shows.
    """
    carriers = [sources[s] for s in (item.source_id, *item.also_covered_by) if s in sources]
    title = clean_title(item.title)
    return bool(carriers) and all(title_excluded(title, s) for s in carriers)


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if parts.port and parts.port != _DEFAULT_PORTS.get(scheme):
        host = f"{host}:{parts.port}"
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith(_TRACKING_PREFIXES)
    )
    return urlunsplit((scheme, host, parts.path or "/", urlencode(query), ""))


def item_id(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class _TextExtractor(HTMLParser):
    """Collects text content, skipping script/style. Entities are decoded by HTMLParser."""

    _SKIP = frozenset({"script", "style"})
    _BLOCK = frozenset({"p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP:
            self._skipping += 1
        elif tag in self._BLOCK:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skipping:
            self._skipping -= 1
        elif tag in self._BLOCK:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return _WS.sub(" ", "".join(parser.parts)).strip()


def truncate(text: str, limit: int = EXCERPT_MAX) -> str:
    """Cut at a word boundary so the result, ellipsis included, is at most `limit` chars."""
    if len(text) <= limit:
        return text
    cut = text[: limit - len(ELLIPSIS) + 1]
    space = cut.rfind(" ")
    # Prefer a word boundary unless it would throw away more than half the text.
    cut = cut[:space] if space > limit // 2 else cut[: limit - len(ELLIPSIS)]
    return cut.rstrip(" ,;:.-\u2013\u2014") + ELLIPSIS


def excerpt(summary: str | None) -> str | None:
    if not summary:
        return None
    return truncate(html_to_text(summary)) or None


def lookback_days(source: Source, topics: TopicsFile) -> int:
    """The longest lookback among the topics this source feeds."""
    by_id = {t.id: t for t in topics.topics}
    days = [
        by_id[t].lookback_days or topics.defaults.lookback_days for t in source.topics if t in by_id
    ]
    return max(days, default=topics.defaults.lookback_days)


def normalize(
    entries: Iterable[RawEntry],
    sources: dict[str, Source],
    topics: TopicsFile,
    now: dt.datetime,
) -> list[Item]:
    """Turn raw entries into candidate Items, dropping ones outside the lookback window."""
    items = []
    for entry in entries:
        source = sources[entry.source_id]
        title = clean_title(entry.title)
        if not title or title_excluded(title, source):
            continue
        published = entry.published.astimezone(dt.UTC) if entry.published else now
        if published > now + FUTURE_TOLERANCE:
            published = now
        if published < now - dt.timedelta(days=lookback_days(source, topics)):
            continue
        canonical = canonical_url(entry.url)
        items.append(
            Item(
                id=item_id(canonical),
                source_id=entry.source_id,
                url=entry.url.strip(),
                canonical_url=canonical,
                title=title,
                excerpt=excerpt(entry.summary) if source.excerpt else None,
                published_at=published,
                first_seen_at=now,
                extra=entry.extra,
            )
        )
    return items
