"""Subreddit sources, via Reddit's public JSON listings (no auth, no API key).

Uses the `hot` listing: `options.min_score` filters on score, and brand-new posts
in `new` haven't had time to earn one. With hourly runs, the 100 hottest posts
cover well over a day of a subreddit's activity.

The item link is the Reddit post itself (the discussion is the content for
leak/discussion subreddits); an external link, when present, goes in `extra`.
Credibility options (`use_flair_credibility`, `fetch_top_comments`) belong to
the parked leaks topic (DESIGN "Parked") and are ignored here. As of 2026-11-22
Reddit refuses both the JSON and RSS listings from this fetcher, so no Reddit
source is enabled.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from ..models import RawEntry
from .rss import FeedParseError

BASE = "https://www.reddit.com"
ACCEPT = "application/json"


def listing_url(subreddit: str) -> str:
    return f"{BASE}/r/{subreddit}/hot.json?limit=100&raw_json=1"


def parse_listing(source_id: str, content: bytes, options: dict[str, Any]) -> list[RawEntry]:
    min_score = int(options.get("min_score", 0))
    try:
        children = json.loads(content)["data"]["children"]
    except (ValueError, KeyError, TypeError) as e:
        raise FeedParseError(f"not a Reddit listing ({type(e).__name__})") from e
    if not isinstance(children, list):
        raise FeedParseError("not a Reddit listing (no children list)")

    entries = []
    for child in children:
        post = child.get("data") or {}
        if child.get("kind") != "t3" or post.get("stickied"):
            continue
        score = int(post.get("score") or 0)
        title = (post.get("title") or "").strip()
        permalink = post.get("permalink") or ""
        if score < min_score or not title or not permalink.startswith("/"):
            continue

        extra: dict[str, Any] = {
            "score": score,
            "upvote_ratio": post.get("upvote_ratio"),
            "num_comments": post.get("num_comments"),
            "flair": post.get("link_flair_text"),
        }
        link = post.get("url_overridden_by_dest")
        if link and not post.get("is_self"):
            extra["link_url"] = link

        created = post.get("created_utc")
        entries.append(
            RawEntry(
                source_id=source_id,
                url=BASE + permalink,
                title=title,
                summary=post.get("selftext") or None,
                published=dt.datetime.fromtimestamp(created, dt.UTC) if created else None,
                extra=extra,
            )
        )
    return entries
