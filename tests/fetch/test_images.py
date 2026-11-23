"""The image a feed itself offers (pipeline/fetch/images.py), against inline feeds."""

from __future__ import annotations

import feedparser
import pytest

from pipeline.fetch.images import clean_image_url, entry_image
from pipeline.fetch.rss import parse_feed

from ..conftest import http_fixture


def entries(items: str) -> list:
    xml = (
        '<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" '
        'xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>t</title>'
        f"{items}</channel></rss>"
    )
    return feedparser.parse(xml.encode()).entries


def one(body: str, link: str = "https://news.example/a") -> str | None:
    [e] = entries(f"<item><title>a</title><link>{link}</link>{body}</item>")
    return entry_image(e)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            '<media:content url="https://img.example/a.jpg" medium="image"/>',
            "https://img.example/a.jpg",
        ),
        (
            '<media:content url="https://img.example/a.jpg" type="image/jpeg"/>',
            "https://img.example/a.jpg",
        ),
        ('<media:content url="https://img.example/a.webp"/>', "https://img.example/a.webp"),
        ('<media:thumbnail url="https://img.example/t.jpg"/>', "https://img.example/t.jpg"),
        (
            '<enclosure url="https://img.example/e.png" type="image/png" length="1"/>',
            "https://img.example/e.png",
        ),
        (
            '<description>&lt;img src="https://img.example/d.jpg"&gt; Text</description>',
            "https://img.example/d.jpg",
        ),
        (
            "<content:encoded><![CDATA[<p>Hi</p><img src='https://img.example/c.jpg'>]]></content:encoded>",
            "https://img.example/c.jpg",
        ),
    ],
)
def test_each_feed_provided_image_kind(body: str, expected: str) -> None:
    assert one(body) == expected


def test_media_content_beats_thumbnail_and_html() -> None:
    body = (
        '<media:thumbnail url="https://img.example/t.jpg"/>'
        '<media:content url="https://img.example/big.jpg" medium="image"/>'
        '<description>&lt;img src="https://img.example/d.jpg"&gt;</description>'
    )
    assert one(body) == "https://img.example/big.jpg"


def test_video_media_and_non_image_enclosures_are_skipped() -> None:
    body = (
        '<media:content url="https://img.example/clip.mp4" type="video/mp4"/>'
        '<enclosure url="https://img.example/ep.mp3" type="audio/mpeg" length="1"/>'
    )
    assert one(body) is None
    body += '<media:content url="https://img.example/still.jpg" type="image/jpeg"/>'
    assert one(body) == "https://img.example/still.jpg"


def test_tracking_pixels_and_icons_are_skipped() -> None:
    body = (
        "<description>"
        '&lt;img src="https://feeds.example/~r/x/~4/pixel.gif" width="1" height="1"&gt;'
        '&lt;img src="https://img.example/icons/share.png"&gt;'
        '&lt;img src="https://img.example/spacer.gif" width="10"&gt;'
        '&lt;img src="https://img.example/photo.jpg" width="640"&gt;</description>'
    )
    assert one(body) == "https://img.example/photo.jpg"


def test_no_image_at_all() -> None:
    assert one("<description>Just text.</description>") is None


@pytest.mark.parametrize(
    ("raw", "base", "expected"),
    [
        ("https://img.example/a.jpg", None, "https://img.example/a.jpg"),
        ("http://img.example/a.jpg", None, "https://img.example/a.jpg"),  # upgraded
        ("//img.example/a.jpg", None, "https://img.example/a.jpg"),
        ("/media/a.jpg", "https://news.example/story", "https://news.example/media/a.jpg"),
        (
            "https://img.example/a.jpg?w=800&amp;h=400",
            None,
            "https://img.example/a.jpg?w=800&h=400",
        ),
        ("  https://img.example/a.jpg  ", None, "https://img.example/a.jpg"),
        ("data:image/png;base64,AAAA", None, None),
        ("javascript:alert(1)", None, None),
        ("ftp://img.example/a.jpg", None, None),
        ("/relative-without-base.jpg", None, None),
        ("https://img.example/a b.jpg", None, None),
        ("https://img.example/" + "a" * 2100 + ".jpg", None, None),
        ("", None, None),
        (None, None, None),
    ],
)
def test_clean_image_url(raw: str | None, base: str | None, expected: str | None) -> None:
    assert clean_image_url(raw, base) == expected


def test_parse_feed_carries_the_image() -> None:
    _, parsed = parse_feed("w", http_fixture("world.rss.xml"))
    assert parsed[0].image_url == "https://static.example.com/images/freedonia.jpg"
    assert parsed[1].image_url is None
