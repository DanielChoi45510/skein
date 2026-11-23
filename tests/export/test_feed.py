"""Feed export: caps, ranking, windows, index, files."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

from pipeline.config import load_config
from pipeline.config.schema import SourceRelevance
from pipeline.config.validate import Config
from pipeline.export import export_feed
from pipeline.export.feed import build_topic_feed
from pipeline.export.models import FeedIndex, TopicFeed
from pipeline.models import Item, SourceHealth

from ..conftest import FIXTURE_CONFIG

NOW = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.UTC)
H = dt.timedelta(hours=1)
D = dt.timedelta(days=1)
CFG = load_config(FIXTURE_CONFIG)
WEIGHTS = {s.id: s.weight for s in CFG.sources.sources}
EXPORT_ITEM_KEYS = {
    "id", "title", "url", "source_id", "published_at", "first_seen_at", "excerpt",
    "importance", "also_covered_by", "collapsed",
}  # fmt: skip


def item(n: int, topic: str = "world", relevance: float = 0.5, published=NOW, **kw) -> Item:
    fields = {
        "id": f"i{n:02d}",
        "source_id": "example-world",
        "url": f"https://example.com/{n}",
        "canonical_url": f"https://example.com/{n}",
        "title": f"Item {n}",
        "published_at": published,
        "first_seen_at": published,
        "topic_id": topic,
        "relevance": relevance,
        "extra": {"score": 1},
    }
    return Item(**(fields | kw))


def topic(topic_id: str, **update):
    t = next(t for t in CFG.topics.topics if t.id == topic_id)
    return t.model_copy(update=update)


def feed(topic_id: str, items: list[Item], **update) -> TopicFeed:
    return build_topic_feed(topic(topic_id, **update), items, CFG.topics, WEIGHTS, NOW)


def flat(f: TopicFeed) -> list:
    return [i for d in f.days for i in d.items]


# ───────────────────────────── ranking and days ─────────────────────────────


def test_ranked_by_importance_within_day() -> None:
    items = [item(1, relevance=0.3), item(2, relevance=0.9), item(3, relevance=0.6)]
    assert [i.id for i in flat(feed("world", items))] == ["i02", "i03", "i01"]


def test_ties_break_by_newest_then_id() -> None:
    # equal relevance; the newer item is fresher so it ranks higher anyway
    items = [item(1, published=NOW - H), item(2), item(3)]
    assert [i.id for i in flat(feed("world", items))] == ["i02", "i03", "i01"]


def test_days_grouped_by_utc_date_newest_first() -> None:
    late = dt.datetime(2026, 11, 20, 23, 30, tzinfo=dt.UTC)
    items = [item(1, published=late), item(2), item(3, published=NOW - 2 * D)]
    f = feed("world", items)
    assert [d.date.isoformat() for d in f.days] == ["2026-11-21", "2026-11-20", "2026-11-19"]


def test_lookback_window() -> None:
    items = [item(1, published=NOW - 7 * D + H), item(2, published=NOW - 7 * D - H)]
    assert [i.id for i in flat(feed("world", items))] == ["i01"]
    assert [i.id for i in flat(feed("world", items, lookback_days=10))] == ["i01", "i02"]


# ───────────────────────────── caps ─────────────────────────────


def test_default_daily_cap_collapses_lowest_never_drops() -> None:
    items = [item(n, relevance=n / 10) for n in range(1, 8)]  # 7 items, one day
    out = flat(feed("world", items))
    assert len(out) == 7
    assert [i.collapsed for i in out] == [False] * 5 + [True] * 2
    assert {i.id for i in out if i.collapsed} == {"i01", "i02"}  # lowest importance


def test_daily_cap_is_per_day() -> None:
    today = [item(n) for n in range(1, 7)]
    yesterday = [item(n, published=NOW - D) for n in range(7, 10)]
    f = feed("world", today + yesterday)
    assert [sum(i.collapsed for i in d.items) for d in f.days] == [1, 0]


def test_explicit_max_per_day() -> None:
    f = feed("world", [item(1), item(2), item(3, published=NOW - D)], max_per_day=1)
    assert [[i.collapsed for i in d.items] for d in f.days] == [[False, True], [False]]


def test_weekly_cap_replaces_daily_default() -> None:
    # gadgets has max_per_week: 10 and no max_per_day → no per-day cap of 5
    items = [item(n, topic="gadgets") for n in range(1, 8)]
    assert not any(i.collapsed for i in flat(feed("gadgets", items)))


def test_weekly_cap_over_trailing_week() -> None:
    items = [
        item(1, topic="gadgets", relevance=0.9, published=NOW - 2 * D),
        item(2, topic="gadgets", relevance=0.5),
        item(3, topic="gadgets", relevance=0.4),
    ]
    out = {i.id: i.collapsed for i in flat(feed("gadgets", items, max_per_week=2))}
    # i01 is older but still most important after decay? 0.9 * 0.5^(48/36) ≈ 0.36 < 0.4
    assert out == {"i01": True, "i02": False, "i03": False}


def test_monthly_cap_only_counts_last_30_days() -> None:
    items = [item(1, relevance=0.9, published=NOW - 35 * D), item(2), item(3, relevance=0.4)]
    f = feed("world", items, max_per_month=1, lookback_days=40)
    out = {i.id: i.collapsed for i in flat(f)}
    assert out == {"i01": False, "i02": False, "i03": True}


def test_target_per_week_caps_listings() -> None:
    items = [item(n, relevance=n / 10) for n in range(1, 5)]
    out = flat(feed("world", items, target_per_week=3))
    assert sum(i.collapsed for i in out) == 1


def test_collapsed_items_sort_last_within_day() -> None:
    # max_per_day=2 lets i01 and i02 through; max_per_week=1 then collapses i02 as well
    items = [item(1, relevance=0.9), item(2, relevance=0.8), item(3, relevance=0.1)]
    f = feed("world", items, max_per_day=2, max_per_week=1)
    assert [(i.id, i.collapsed) for i in f.days[0].items] == [
        ("i01", False),
        ("i02", True),
        ("i03", True),
    ]


# ───────────────────────────── export_feed ─────────────────────────────


def run_export(tmp_path: Path, items: list[Item], cfg: Config = CFG, health=None) -> FeedIndex:
    return export_feed(tmp_path, cfg, items, health or {}, NOW)


def test_writes_index_and_every_topic(tmp_path: Path) -> None:
    run_export(tmp_path, [item(1)])
    names = sorted(p.name for p in (tmp_path / "feed" / "topics").iterdir())
    assert names == sorted(f"{t.id}.json" for t in CFG.topics.topics)
    index = FeedIndex.model_validate_json((tmp_path / "feed" / "index.json").read_text())
    assert index.generated_at == NOW
    for path in (tmp_path / "feed" / "topics").iterdir():
        TopicFeed.model_validate_json(path.read_text())


def test_exported_items_have_only_public_fields(tmp_path: Path) -> None:
    run_export(tmp_path, [item(1, excerpt="Short.")])
    data = json.loads((tmp_path / "feed" / "topics" / "world.json").read_text())
    [exported] = data["days"][0]["items"]
    assert set(exported) == EXPORT_ITEM_KEYS  # no `extra`, relevance internals, etc.


def test_hidden_and_unrouted_items_are_not_exported(tmp_path: Path) -> None:
    items = [
        item(1),
        item(2, hidden_reason="duplicate", duplicate_of="i01"),
        item(3, relevance=0.1),  # below the fixture threshold (0.30)
        item(4, topic_id=None),
        item(5, source_id="removed-source"),
        item(6, topic="removed-topic"),
    ]
    run_export(tmp_path, items)
    data = json.loads((tmp_path / "feed" / "topics" / "world.json").read_text())
    assert [i["id"] for d in data["days"] for i in d["items"]] == ["i01"]


def with_title_exclude(*patterns: str) -> Config:
    sources = [
        s.model_copy(update={"title_exclude": list(patterns)}) if s.id == "example-world" else s
        for s in CFG.sources.sources
    ]
    return dataclasses.replace(CFG, sources=CFG.sources.model_copy(update={"sources": sources}))


def test_title_exclude_hides_stored_items(tmp_path: Path) -> None:
    items = [
        item(1, title="NTR.TO | Stock Price"),
        item(2, title="Real news"),
        item(3, title="ABC | Stock Price", also_covered_by=["example-hn"]),  # hn keeps it
    ]
    run_export(tmp_path, items, with_title_exclude(r"\| stock price$"))
    data = json.loads((tmp_path / "feed" / "topics" / "world.json").read_text())
    assert sorted(i["id"] for d in data["days"] for i in d["items"]) == ["i02", "i03"]


def test_stored_titles_are_cleaned_on_export(tmp_path: Path) -> None:
    run_export(tmp_path, [item(1, title="<i>Grand Theft Auto VI</i> &amp; time")])
    data = json.loads((tmp_path / "feed" / "topics" / "world.json").read_text())
    assert data["days"][0]["items"][0]["title"] == "Grand Theft Auto VI & time"


def test_index_summaries(tmp_path: Path) -> None:
    items = [item(n) for n in range(1, 8)] + [item(9, topic="gadgets", first_seen_at=NOW - H)]
    index = run_export(tmp_path, items)
    topics = {t.id: t for g in index.groups for t in g.topics}
    assert [g.id for g in index.groups] == ["news", "tech", "games"]
    assert [t.id for t in index.groups[0].topics] == ["world", "politics", "markets"]
    assert (topics["world"].visible_count, topics["world"].collapsed_count) == (5, 2)
    assert topics["world"].latest_first_seen_at == NOW
    assert topics["gadgets"].latest_first_seen_at == NOW - H
    assert topics["politics"].latest_first_seen_at is None
    assert topics["world"].has_sources
    assert not topics["markets"].has_sources  # no source at all
    assert not topics["leaks"].has_sources  # only a disabled source


def test_source_names_fall_back(tmp_path: Path) -> None:
    renamed = [
        s.model_copy(update={"name": "Named"}) if s.id == "example-world" else s
        for s in CFG.sources.sources
    ]
    cfg = dataclasses.replace(CFG, sources=CFG.sources.model_copy(update={"sources": renamed}))
    health = {
        "example-world": SourceHealth(feed_title="Feed Title Ignored"),
        "example-gadgets": SourceHealth(feed_title="Gadget Lab"),
    }
    summaries = run_export(tmp_path, [], cfg, health).sources
    assert {s.paywall for s in summaries} == {"none"}  # fixture default
    names = {s.id: s.name for s in summaries}
    assert names["example-world"] == "Named"
    assert names["example-gadgets"] == "Gadget Lab"
    assert names["example-hn"] == "example-hn"


def test_stale_topic_files_removed(tmp_path: Path) -> None:
    stale = tmp_path / "feed" / "topics" / "old-topic.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")
    run_export(tmp_path, [])
    assert not stale.exists()


def exported_ids(tmp_path: Path, items: list[Item], topic_id: str = "world") -> list[str]:
    run_export(tmp_path, items)
    data = json.loads((tmp_path / "feed" / "topics" / f"{topic_id}.json").read_text())
    return [i["id"] for d in data["days"] for i in d["items"]]


def test_disabled_source_items_are_hidden_immediately(tmp_path: Path) -> None:
    # example-disabled is a disabled rss source feeding `world` in the fixture config
    items = [item(1), item(2, source_id="example-disabled", relevance=0.9)]
    assert exported_ids(tmp_path, items) == ["i01"]


def test_story_shared_with_an_enabled_source_stays(tmp_path: Path) -> None:
    shared = item(2, source_id="example-disabled", also_covered_by=["example-world"])
    assert exported_ids(tmp_path, [shared]) == ["i02"]


def test_disabled_skip_source_does_not_rescue_low_scores(tmp_path: Path) -> None:
    disabled_skip = CFG.sources.model_copy(
        update={
            "sources": [
                s.model_copy(update={"relevance": SourceRelevance(skip=True)})
                if s.id == "example-disabled"
                else s
                for s in CFG.sources.sources
            ]
        }
    )
    cfg = dataclasses.replace(CFG, sources=disabled_skip)
    low = item(1, relevance=0.1, also_covered_by=["example-disabled"])  # below 0.30
    run_export(tmp_path, [low], cfg)
    data = json.loads((tmp_path / "feed" / "topics" / "world.json").read_text())
    assert data["days"] == []
