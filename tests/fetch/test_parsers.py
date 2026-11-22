"""RSS / Atom / Reddit parsing against the synthetic fixtures."""

from __future__ import annotations

import datetime as dt

import pytest

from pipeline.fetch.reddit import listing_url, parse_listing
from pipeline.fetch.rss import FeedParseError, parse_feed

from ..conftest import http_fixture

UTC = dt.UTC


# ───────────────────────────── RSS ─────────────────────────────


def test_rss_feed() -> None:
    title, entries = parse_feed("w", http_fixture("world.rss.xml"))
    assert title == "Example Times > World"
    # the entry without a link is skipped
    assert [e.title for e in entries] == [
        "Coalition Talks Resume After Close Election in Freedonia",
        "Central Bank of Sylvania Holds Rates Steady",
        "Item Without a Date",
    ]
    first = entries[0]
    assert first.source_id == "w"
    # tracking params are left for normalization (step b)
    assert first.url.startswith(
        "https://www.example.com/2026/11/21/world/freedonia-coalition.html?"
    )
    assert first.summary is not None and "<b>third</b>" in first.summary
    assert first.published == dt.datetime(2026, 11, 21, 10, 30, tzinfo=UTC)


def test_rss_dates_are_converted_to_utc() -> None:
    _, entries = parse_feed("w", http_fixture("world.rss.xml"))
    # "Fri, 20 Nov 2026 18:15:00 -0500"
    assert entries[1].published == dt.datetime(2026, 11, 20, 23, 15, tzinfo=UTC)
    assert entries[2].published is None


def test_rss_comments_link_kept_in_extra() -> None:
    title, entries = parse_feed("hn", http_fixture("hn.rss.xml"))
    assert title == "Example News: Front Page"
    assert entries[0].url == "https://blog.example.dev/workouts"
    assert entries[0].extra == {"comments_url": "https://hn.example.net/item?id=1001"}


def test_atom_feed() -> None:
    title, entries = parse_feed("g", http_fixture("gadgets.atom"))
    assert title == "Example Gadget Lab"
    assert [e.url for e in entries] == [
        "https://reviews.example.org/desk-lamps-tested",
        "https://reviews.example.org/example-book-14-review",
    ]
    # `published` wins over `updated`; +01:00 converted to UTC
    assert entries[0].published == dt.datetime(2026, 11, 21, 6, 45, tzinfo=UTC)
    # no `published`: falls back to `updated`
    assert entries[1].published == dt.datetime(2026, 11, 20, 15, 0, tzinfo=UTC)


@pytest.mark.parametrize("content", [b"<html><body>Not a feed</body></html>", b"\x00\x01garbage"])
def test_non_feed_raises(content: bytes) -> None:
    with pytest.raises(FeedParseError):
        parse_feed("x", content)


def test_empty_but_valid_feed_has_no_entries() -> None:
    content = b'<?xml version="1.0"?><rss version="2.0"><channel><title>T</title></channel></rss>'
    assert parse_feed("x", content) == ("T", [])


# ───────────────────────────── Reddit ─────────────────────────────


def test_listing_url() -> None:
    assert (
        listing_url("Foo_Bar") == "https://www.reddit.com/r/Foo_Bar/hot.json?limit=100&raw_json=1"
    )


def test_reddit_listing() -> None:
    entries = parse_listing("r", http_fixture("reddit_hot.json"), {"min_score": 50})
    # stickied post, low-score post and the non-post child are skipped
    assert [e.title for e in entries] == [
        "House committee releases budget numbers",
        "Summary of today's hearing, with sources",
    ]
    link_post, self_post = entries
    assert (
        link_post.url
        == "https://www.reddit.com/r/ExampleNews/comments/bbb2/house_committee_budget/"
    )
    assert link_post.extra == {
        "score": 512,
        "upvote_ratio": 0.93,
        "num_comments": 88,
        "flair": "Policy",
        "link_url": "https://news.example.com/budget-numbers",
    }
    assert link_post.summary is None
    assert link_post.published == dt.datetime.fromtimestamp(1795262400, UTC)

    assert "link_url" not in self_post.extra
    assert self_post.summary == "Three witnesses testified. Key numbers: 4.2 billion & 12 agencies."


def test_reddit_min_score_defaults_to_zero() -> None:
    entries = parse_listing("r", http_fixture("reddit_hot.json"), {})
    assert len(entries) == 3


@pytest.mark.parametrize("content", [b"not json", b"{}", b'{"data": {"children": null}}', b"[]"])
def test_reddit_malformed_listing_raises(content: bytes) -> None:
    with pytest.raises(FeedParseError):
        parse_listing("r", content, {})
