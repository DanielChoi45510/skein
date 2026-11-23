"""The image a feed itself offers for an entry (CLAUDE.md principle 3, DESIGN §6.1).

Only what the feed provides, in this order:
1. `media:content` that is an image (by `medium`, MIME type or file extension),
2. `media:thumbnail`,
3. an image `<enclosure>`,
4. the first `<img>` in the entry's own description / content.

Article pages are never fetched, and images are never downloaded, stored or
re-hosted: only the URL is kept, and the reader's browser loads it from the
source. URLs are cleaned conservatively: http(s) only (http upgraded to https,
since the site is served over https), protocol-relative and relative URLs
resolved against the entry's link, nothing over 2048 characters, and likely
tracking pixels / icons skipped (tiny declared sizes, tracker paths).
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

MAX_URL = 2048
MIN_SIDE = 40  # px: a declared width or height below this is a pixel, icon or spacer
_IMAGE_EXT = re.compile(r"\.(?:jpe?g|png|gif|webp|avif)(?:$|[?#])", re.IGNORECASE)
# Trackers, counters and decorations that feeds embed as images.
_NOT_A_PICTURE = re.compile(
    r"(?:pixel|beacon|tracking|/~r/|/~ff/|feedburner|doubleclick|gravatar|emoji|"
    r"spacer|blank\.gif|1x1|share[-_]?button|/icons?/|favicon)",
    re.IGNORECASE,
)


def clean_image_url(raw: str | None, base: str | None = None) -> str | None:
    """A safe absolute https URL for an image, or None."""
    if not raw:
        return None
    url = html.unescape(raw).strip()
    if not url or any(c.isspace() for c in url):
        return None
    if url.startswith("//"):
        url = "https:" + url
    elif base and not urlsplit(url).scheme:
        url = urljoin(base, url)
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None  # data:, javascript:, ftp:, … never
    if parts.scheme == "http":
        url = "https" + url[4:]
    if len(url) > MAX_URL or _NOT_A_PICTURE.search(url):
        return None
    return url


def _too_small(attrs: Mapping[str, Any]) -> bool:
    for key in ("width", "height"):
        value = str(attrs.get(key) or "").strip().removesuffix("px")
        if value.isdigit() and int(value) < MIN_SIDE:
            return True
    return False


def _is_image(media: Mapping[str, Any]) -> bool:
    medium = (media.get("medium") or "").lower()
    mime = (media.get("type") or "").lower()
    if medium:
        return medium == "image"
    if mime:
        return mime.startswith("image/")
    return bool(_IMAGE_EXT.search(media.get("url") or ""))


class _FirstImage(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.candidates: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "img":
            self.candidates.append(dict(attrs))


def _html_images(fragments: Iterable[str | None]) -> Iterable[dict[str, str | None]]:
    for fragment in fragments:
        if fragment and "<img" in fragment.lower():
            parser = _FirstImage()
            parser.feed(fragment)
            parser.close()
            yield from parser.candidates


def entry_image(entry: Mapping[str, Any]) -> str | None:
    """The first usable image URL a feedparser entry offers, or None."""
    base = (entry.get("link") or "").strip() or None

    def first(candidates: Iterable[Mapping[str, Any]], key: str) -> str | None:
        for c in candidates:
            if _too_small(c):
                continue
            if url := clean_image_url(c.get(key), base):
                return url
        return None

    found = (
        first((m for m in entry.get("media_content") or [] if _is_image(m)), "url")
        or first(entry.get("media_thumbnail") or [], "url")
        or first(
            (
                e
                for e in entry.get("enclosures") or []
                if (e.get("type") or "").lower().startswith("image/")
            ),
            "href",
        )
    )
    if found:
        return found
    fragments = [entry.get("summary"), *(c.get("value") for c in entry.get("content") or [])]
    return first(_html_images(fragments), "src")
