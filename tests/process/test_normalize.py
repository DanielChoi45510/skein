"""Normalization: canonical URLs, excerpts, dates, lookback."""

from __future__ import annotations

import datetime as dt
import re

import pytest

from pipeline.config import load_config
from pipeline.models import RawEntry
from pipeline.process.normalize import (
    EXCERPT_MAX,
    canonical_url,
    clean_title,
    excerpt,
    excluded_by_title,
    html_to_text,
    item_id,
    lookback_days,
    normalize,
    title_excluded,
    truncate,
)

from ..conftest import FIXTURE_CONFIG, REPO_CONFIG

NOW = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.UTC)
CFG = load_config(FIXTURE_CONFIG)
SOURCES = {s.id: s for s in CFG.sources.sources}


def raw(**kw) -> RawEntry:
    base = {"source_id": "example-world", "url": "https://example.com/a", "title": "T"}
    return RawEntry(**(base | kw))


# ───────────────────────────── URLs ─────────────────────────────


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/a", "https://example.com/a"),
        ("HTTPS://WWW.Example.COM/Path/Case", "https://www.example.com/Path/Case"),
        ("https://example.com/a#section", "https://example.com/a"),
        ("https://example.com", "https://example.com/"),
        ("https://example.com:443/a", "https://example.com/a"),
        ("http://example.com:80/a", "http://example.com/a"),
        ("https://example.com:8443/a", "https://example.com:8443/a"),
        ("https://example.com/a?utm_source=rss&utm_medium=feed", "https://example.com/a"),
        ("https://example.com/a?smid=rss&partner=x&ref=hn", "https://example.com/a"),
        ("https://example.com/a?fbclid=1&gclid=2&mc_cid=3&mc_eid=4", "https://example.com/a"),
        ("https://example.com/a?UTM_Source=x&id=5", "https://example.com/a?id=5"),
        ("https://example.com/a?b=2&a=1", "https://example.com/a?a=1&b=2"),
        ("https://example.com/a?id=5&utm_source=x&page=2", "https://example.com/a?id=5&page=2"),
        ("  https://example.com/a  ", "https://example.com/a"),
    ],
)
def test_canonical_url(url: str, expected: str) -> None:
    assert canonical_url(url) == expected


def test_item_id_is_stable_hash_of_canonical_url() -> None:
    a = item_id(canonical_url("https://example.com/a?utm_source=x"))
    b = item_id(canonical_url("https://EXAMPLE.com/a#frag"))
    assert a == b
    assert re.fullmatch(r"[0-9a-f]{16}", a)


# ───────────────────────────── text ─────────────────────────────


@pytest.mark.parametrize(
    ("html", "text"),
    [
        ("<p>Hello <b>world</b></p>", "Hello world"),
        ("<p>One</p><p>Two</p>", "One Two"),
        ("Line<br>break", "Line break"),
        ("Fish &amp; chips &lt;3 &#8217;s", "Fish & chips <3 \u2019s"),
        ("<script>alert(1)</script>Safe<style>p{}</style>", "Safe"),
        ("  lots\n\n of \t space  ", "lots of space"),
        ("plain text, no tags", "plain text, no tags"),
    ],
)
def test_html_to_text(html: str, text: str) -> None:
    assert html_to_text(html) == text


def test_truncate_short_text_untouched() -> None:
    assert truncate("short") == "short"
    exact = "x" * EXCERPT_MAX
    assert truncate(exact) == exact


def test_truncate_at_word_boundary() -> None:
    text = ("word " * 100).strip()  # 499 chars
    out = truncate(text)
    assert len(out) <= EXCERPT_MAX
    assert out.endswith("word…")


def test_truncate_without_spaces_hard_cuts() -> None:
    out = truncate("x" * 1000)
    assert len(out) == EXCERPT_MAX
    assert out.endswith("…")


def test_truncate_strips_trailing_punctuation() -> None:
    text = "a" * 250 + ", " + "b" * 100
    assert truncate(text) == "a" * 250 + "…"


def test_excerpt_none_and_empty() -> None:
    assert excerpt(None) is None
    assert excerpt("") is None
    assert excerpt("<p> </p>") is None


# ───────────────────────────── normalize ─────────────────────────────


def test_normalize_builds_item() -> None:
    published = dt.datetime(2026, 11, 21, 10, 30, tzinfo=dt.UTC)
    [item] = normalize(
        [
            raw(
                url="https://example.com/a?utm_source=x",
                title="  Spaced   <canvas> title ",
                summary="<p>Body &amp; more</p>",
                published=published,
                extra={"score": 5},
            )
        ],
        SOURCES,
        CFG.topics,
        NOW,
    )
    assert item.url == "https://example.com/a?utm_source=x"  # original link kept
    assert item.canonical_url == "https://example.com/a"
    assert item.id == item_id("https://example.com/a")
    assert item.title == "Spaced <canvas> title"  # titles are text, not HTML
    assert item.excerpt == "Body & more"
    assert item.published_at == published
    assert item.first_seen_at == NOW
    assert item.extra == {"score": 5}
    assert item.visible


def test_missing_date_uses_now() -> None:
    [item] = normalize([raw(published=None)], SOURCES, CFG.topics, NOW)
    assert item.published_at == NOW


def test_future_date_is_clamped() -> None:
    future = NOW + dt.timedelta(hours=3)
    [item] = normalize([raw(published=future)], SOURCES, CFG.topics, NOW)
    assert item.published_at == NOW


def test_small_clock_skew_is_tolerated() -> None:
    soon = NOW + dt.timedelta(minutes=2)
    [item] = normalize([raw(published=soon)], SOURCES, CFG.topics, NOW)
    assert item.published_at == soon


def test_non_utc_dates_are_converted() -> None:
    est = dt.timezone(dt.timedelta(hours=-5))
    [item] = normalize(
        [raw(published=dt.datetime(2026, 11, 21, 6, 0, tzinfo=est))], SOURCES, CFG.topics, NOW
    )
    assert item.published_at == dt.datetime(2026, 11, 21, 11, 0, tzinfo=dt.UTC)
    assert item.published_at.tzinfo == dt.UTC


def test_empty_title_is_dropped() -> None:
    assert normalize([raw(title="   ")], SOURCES, CFG.topics, NOW) == []


def test_lookback_cut() -> None:
    old = NOW - dt.timedelta(days=7, minutes=1)
    edge = NOW - dt.timedelta(days=7)
    items = normalize(
        [
            raw(url="https://e.com/old", published=old),
            raw(url="https://e.com/edge", published=edge),
        ],
        SOURCES,
        CFG.topics,
        NOW,
    )
    assert [i.url for i in items] == ["https://e.com/edge"]


def test_lookback_uses_longest_topic_override() -> None:
    topics = CFG.topics.model_copy(
        update={
            "topics": [
                t.model_copy(update={"lookback_days": 3}) if t.id == "gadgets" else t
                for t in CFG.topics.topics
            ]
        }
    )
    # example-gadgets feeds gadgets (3 days, overridden) and trackers (default 7)
    assert lookback_days(SOURCES["example-gadgets"], topics) == 7
    # example-world feeds only world (default 7)
    assert lookback_days(SOURCES["example-world"], topics) == 7
    only_gadgets = SOURCES["example-gadgets"].model_copy(update={"topics": ["gadgets"]})
    assert lookback_days(only_gadgets, topics) == 3


def test_excerpt_disabled_per_source() -> None:
    entry = raw(source_id="example-hn", summary="<p>Article URL: https://x Points: 300</p>")
    [item] = normalize([entry], SOURCES, CFG.topics, NOW)
    assert item.excerpt is None


# ───────────────────────────── titles ─────────────────────────────


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("What Is the Fantasy in <i>Grand Theft Auto</i> Really About?",
         "What Is the Fantasy in Grand Theft Auto Really About?"),
        ("<em>Grand Theft Auto VI</em> Is Really Weird", "Grand Theft Auto VI Is Really Weird"),
        ('<a href="x">Link</a> and <span class="c">span</span>', "Link and span"),
        ("Fish &amp; chips &#8217;s", "Fish & chips \u2019s"),
        ("&lt;i&gt;Double-encoded&lt;/i&gt;", "Double-encoded"),
        ("New <canvas> API ships", "New <canvas> API ships"),  # literal text, not markup
        ("AT&T  beats  estimates", "AT&T beats estimates"),
        ("Plain", "Plain"),
    ],
)  # fmt: skip
def test_clean_title(title: str, expected: str) -> None:
    assert clean_title(title) == expected
    assert clean_title(expected) == expected  # idempotent: safe to apply again at export


def test_normalize_cleans_titles() -> None:
    [item] = normalize([raw(title="<i>Madden</i>  &amp; more")], SOURCES, CFG.topics, NOW)
    assert item.title == "Madden & more"


def with_excludes(source_id: str, *patterns: str) -> dict:
    return SOURCES | {
        source_id: SOURCES[source_id].model_copy(update={"title_exclude": list(patterns)})
    }


def test_title_exclude_drops_matching_entries_case_insensitively() -> None:
    sources = with_excludes("example-world", r"\| stock price & latest news")
    entries = [
        raw(url="https://example.com/1", title="Nutrien Ltd (NTR.TO) | Stock Price & Latest News"),
        raw(url="https://example.com/2", title="EU and Indonesia sign trade deal"),
    ]
    assert [i.title for i in normalize(entries, sources, CFG.topics, NOW)] == [
        "EU and Indonesia sign trade deal"
    ]


def test_title_exclude_is_per_source() -> None:
    sources = with_excludes("example-world", "quote page")
    assert normalize([raw(source_id="example-hn", title="A quote page")], sources, CFG.topics, NOW)


def test_excluded_by_title_needs_every_carrying_source_to_exclude() -> None:
    from pipeline.models import Item

    sources = with_excludes("example-world", "^ticker$")
    stored = Item(
        id="x",
        source_id="example-world",
        url="https://example.com/x",
        canonical_url="https://example.com/x",
        title="<b>TICKER</b>",  # cleaned before matching
        published_at=NOW,
        first_seen_at=NOW,
    )
    assert excluded_by_title(stored, sources)
    assert not excluded_by_title(
        stored.model_copy(update={"also_covered_by": ["example-hn"]}), sources
    )
    assert not excluded_by_title(stored.model_copy(update={"source_id": "removed"}), sources)


REUTERS_QUOTE_PAGES = [
    "Nutrien Ltd (NTR.TO) | Stock Price & Latest News - Reuters",
    "2694.JSF - | Stock Price & Latest News - Reuters",
    "iShares SLI UCITS (DE) ETF (SSMIEX.DE) | Stock Price & Latest News - Reuters",
    "THO.TH - Reuters",
    "ABP.MI - Reuters",
]
REUTERS_NEWS = [
    "EU and Indonesia sign trade deal after 10 years of negotiations - Reuters",
    "EU leaders' chair proposes new cuts to EU 2028-2034 budget draft, suggests digital tax"
    " - Reuters",
]


def test_committed_reuters_markets_patterns() -> None:
    """The real config's patterns, on real titles stored 2026-11-22."""
    source = next(s for s in load_config(REPO_CONFIG).sources.sources if s.id == "reuters-markets")
    assert all(title_excluded(t, source) for t in REUTERS_QUOTE_PAGES)
    assert not any(title_excluded(t, source) for t in REUTERS_NEWS)
