"""Thread lifecycle, pruning and keyword titles (DESIGN §5)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pytest

from pipeline.config import load_config
from pipeline.models import Item, Thread
from pipeline.process.lifecycle import (
    PROMOTE_MIN_CORROBORATION,
    advance,
    keyword_title,
    prune,
    retitle,
)
from pipeline.process.threads import PENDING_WINDOW

from ..conftest import FIXTURE_CONFIG

NOW = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.UTC)
D = dt.timedelta(days=1)
H = dt.timedelta(hours=1)
CFG = load_config(FIXTURE_CONFIG)  # defaults: cooling 3, dormant 14, archive 60 days
TOPICS = CFG.topics


def item(item_id: str, title: str = "Headline", *, at: dt.datetime = NOW, **kw) -> Item:
    fields = {
        "id": item_id,
        "source_id": "example-world",
        "url": f"https://example.com/{item_id}",
        "canonical_url": f"https://example.com/{item_id}",
        "title": title,
        "published_at": at,
        "first_seen_at": at,
        "topic_id": "world",
    }
    return Item(**(fields | kw))


def thread(
    thread_id: str = "t1",
    state: str = "active",
    *,
    created: dt.datetime = NOW,
    last: dt.datetime = NOW,
    items: list[str] | None = None,
    topic: str = "world",
    kind: str = "story",
) -> Thread:
    return Thread(
        id=thread_id,
        topic_id=topic,
        kind=kind,
        title="Title",
        state=state,
        created_at=created,
        last_item_at=last,
        item_ids=items if items is not None else ["a"],
    )


def run(threads: list[Thread], items: list[Item] = (), now: dt.datetime = NOW):
    by_id = {t.id: t for t in threads}
    centroids = {t.id: np.ones(2, np.float32) for t in threads}
    advance(by_id, centroids, {i.id: i for i in items}, TOPICS, now)
    return by_id, centroids


# ───────────────────────────── pending ─────────────────────────────


def test_pending_with_second_item_is_promoted_and_retitled() -> None:
    items = [
        item("a", "Germany election: SPD wins Berlin vote", at=NOW - 2 * H),
        item("b", "SPD wins Berlin and Germany election", at=NOW - H),
    ]
    t = thread(state="pending", created=NOW - 2 * H, items=["a", "b"])
    threads, centroids = run([t], items)
    assert threads["t1"].state == "active"
    assert threads["t1"].title == "SPD · Wins · Berlin · Germany"
    assert "t1" in centroids


def test_corroborated_single_item_is_promoted() -> None:
    covered = [f"s{n}" for n in range(PROMOTE_MIN_CORROBORATION)]
    items = [item("a", "Big story", also_covered_by=covered)]
    threads, _ = run([thread(state="pending", items=["a"])], items)
    assert threads["t1"].state == "active"
    assert threads["t1"].title == "Big story"  # one headline: the headline is the title


def test_single_item_without_corroboration_stays_pending() -> None:
    items = [item("a", also_covered_by=["s1"])]
    threads, centroids = run([thread(state="pending", created=NOW - H, items=["a"])], items)
    assert threads["t1"].state == "pending"
    assert "t1" in centroids  # still matchable within 72 h


def test_pending_expires_after_72_hours() -> None:
    created = NOW - PENDING_WINDOW - H
    items = [item("a", at=created, also_covered_by=["s1", "s2", "s3"])]
    threads, centroids = run([thread(state="pending", created=created, last=created)], items)
    assert threads["t1"].state == "pending"  # never promoted late; its item shows alone
    assert "t1" not in centroids  # no longer matchable


def test_promoted_backfill_thread_takes_the_state_for_its_age() -> None:
    old = NOW - 5 * D
    items = [item("a", "Old story here", at=old - H), item("b", "Old story there", at=old)]
    t = thread(state="pending", created=NOW - H, last=old, items=["a", "b"])
    threads, _ = run([t], items)
    assert threads["t1"].state == "cooling"


# ───────────────────────────── timings ─────────────────────────────


@pytest.mark.parametrize(
    ("age", "state"),
    [
        (0 * D, "active"),
        (3 * D - H, "active"),
        (3 * D, "cooling"),
        (14 * D - H, "cooling"),
        (14 * D, "dormant"),
        (60 * D - H, "dormant"),
        (60 * D, "archived"),
    ],
)
def test_state_follows_age_of_newest_item(age: dt.timedelta, state: str) -> None:
    threads, centroids = run([thread(created=NOW - 90 * D, last=NOW - age)])
    assert threads["t1"].state == state
    assert ("t1" in centroids) is (state != "archived")


def test_topic_override_timings() -> None:
    topics = TOPICS.model_copy(
        update={
            "topics": [
                t.model_copy(update={"cooling_after_days": 30, "dormant_after_days": 120})
                if t.id == "world"
                else t
                for t in TOPICS.topics
            ]
        }
    )
    t = thread(created=NOW - 90 * D, last=NOW - 20 * D)
    threads = {"t1": t}
    advance(threads, {}, {}, topics, NOW)
    assert threads["t1"].state == "active"


@pytest.mark.parametrize("state", ["cooling", "dormant"])
def test_new_item_revives(state: str) -> None:
    threads, _ = run([thread(state=state, created=NOW - 30 * D, last=NOW - H)])
    assert threads["t1"].state == "active"


def test_archived_is_final() -> None:
    threads, centroids = run([thread(state="archived", created=NOW - 90 * D, last=NOW)])
    assert threads["t1"].state == "archived"
    assert "t1" not in centroids


# ───────────────────────────── tracker and fixed ─────────────────────────────


@pytest.mark.parametrize(
    ("topic", "kind", "thread_id"),
    [("trackers", "tracker", "trackers--phones"), ("markets", "fixed", "markets--energy")],
)
@pytest.mark.parametrize("age", [0 * D, 4 * D, 30 * D, 400 * D])
def test_tracker_and_fixed_threads_stay_active_forever(
    topic: str, kind: str, thread_id: str, age: dt.timedelta
) -> None:
    """DESIGN §5: they never cool, go dormant or archive, however long they're quiet."""
    t = thread(thread_id, created=NOW - 500 * D, last=NOW - age, topic=topic, kind=kind)
    threads, _ = run([t])
    assert threads[thread_id].state == "active"


def test_predefined_thread_removed_from_config_is_archived() -> None:
    t = thread("trackers--watches", topic="trackers", kind="tracker")
    threads, _ = run([t])
    assert threads["trackers--watches"].state == "archived"


@pytest.mark.parametrize("topic", ["removed-topic", "gadgets"])  # gone, or now flat
def test_threads_of_unthreaded_topics_are_archived(topic: str) -> None:
    threads, centroids = run([thread(topic=topic)])
    assert threads["t1"].state == "archived"
    assert centroids == {}


# ───────────────────────────── pruning ─────────────────────────────


def test_prune_drops_unloaded_pending_and_archived_threads_only() -> None:
    threads = {
        t.id: t
        for t in [
            thread("p-gone", "pending", items=["old"]),
            thread("p-here", "pending", items=["x"]),
            thread("a-gone", "archived", items=["old"]),
            thread("d-gone", "dormant", items=["old"]),
            thread("trackers--phones", items=[], topic="trackers", kind="tracker"),
        ]
    }
    centroids = {"p-gone": np.ones(2), "p-here": np.ones(2)}
    gone = prune(threads, centroids, loaded={"x"})
    assert sorted(gone) == ["a-gone", "p-gone"]
    assert sorted(threads) == ["d-gone", "p-here", "trackers--phones"]
    assert sorted(centroids) == ["p-here"]


# ───────────────────────────── titles ─────────────────────────────


@pytest.mark.parametrize(
    ("titles", "expected"),
    [
        # Real headline pairs the owner labeled as one thread (tests/fixtures/threading).
        (["Introducing GPT-6.2 Astra and Sol",
          "[AINews] GPT-6.2 Astra, the #2 Frontier Model is better and 20%-600% cheaper"],
         "GPT-6.2 · Astra"),
        (["Steve Rosenberg: Historic talks with Xi and Trump are a coup for Putin",
          "BBC correspondents discuss what Trump, Xi and Putin got out of historic talks"],
         "Trump · Xi · Putin · Historic"),
        (["Democrats Clinch 258 House Seats, an Election-Year Record This Century",
          "Democrats clinch a historic House majority of at least 258 seats"],
         "Democrats · Clinch · House · Seats"),
        (["Gemini 4 Hydrogen: a faster model for robotics", "Introducing Gemini 4 Neon"],
         "Gemini · 4"),
        # Fewer than two shared words: the newest headline.
        (["Measles Is Officially Back in the United States",
          "U.S. Loses Its Measles Elimination Status"],
         "U.S. Loses Its Measles Elimination Status"),
        (["Only one headline"], "Only one headline"),
        ([], ""),
    ],
)  # fmt: skip
def test_keyword_title(titles: list[str], expected: str) -> None:
    assert keyword_title(titles) == expected


def test_keyword_title_prefers_words_in_more_headlines() -> None:
    titles = [
        "OpenAI board meets on funding",
        "OpenAI funding round closes",
        "OpenAI funding: what investors got",
    ]
    assert keyword_title(titles, max_terms=2) == "OpenAI · Funding"


def test_retitle_uses_loaded_items_oldest_first() -> None:
    items = {
        "a": item("a", "<i>Fed</i> holds rates steady", at=NOW - 2 * H),
        "b": item("b", "Fed rates decision: holds steady again", at=NOW - H),
    }
    t = thread(items=["b", "a", "unloaded"])
    retitle(t, items)
    assert t.title == "Fed · Rates · Holds · Steady"


def test_retitle_pending_uses_headline_and_keeps_predefined_titles() -> None:
    items = {"a": item("a", "A &amp; B")}
    pending = thread(state="pending", items=["a"])
    retitle(pending, items)
    assert pending.title == "A & B"
    tracker = thread("trackers--phones", topic="trackers", kind="tracker", items=["a"])
    retitle(tracker, items)
    assert tracker.title == "Title"
