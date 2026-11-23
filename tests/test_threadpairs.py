"""The labeled-set builder (python -m pipeline.threadpairs), offline with the hashing embedder."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from pipeline.config import load_config
from pipeline.models import Item
from pipeline.process.embed import HashingEmbedder
from pipeline.state import save_items
from pipeline.threadpairs import (
    AUTO_MODES,
    BANDS,
    Pair,
    PairSide,
    all_pairs,
    bands_between,
    eligible,
    embed_items,
    main,
    routing_sample,
    sample_pairs,
)

from .conftest import FIXTURE_CONFIG

CFG = load_config(FIXTURE_CONFIG)
NOW = dt.datetime.now(dt.UTC).replace(microsecond=0)


def item(item_id: str, title: str, topic: str = "world", **kw) -> Item:
    fields = {
        "id": item_id,
        "source_id": "example-world",
        "url": f"https://example.com/{item_id}",
        "canonical_url": f"https://example.com/{item_id}",
        "title": title,
        "published_at": NOW,
        "first_seen_at": NOW,
        "topic_id": topic,
        "relevance": 0.9,
    }
    return Item(**(fields | kw))


ITEMS = {
    i.id: i
    for i in [
        item("a", "Germany election: SPD wins Berlin vote"),
        item("b", "SPD wins Germany election in Berlin"),
        item("c", "Japan election results announced"),
        item("low", "Germany election low score", relevance=0.1),  # below threshold
        item("dup", "Germany election duplicate", hidden_reason="duplicate"),
        item("gone", "Germany election", source_id="example-disabled"),
        item("flat", "Desk lamp review", topic="gadgets", source_id="example-gadgets"),
        item("ph", "New phone review", topic="trackers", source_id="example-gadgets"),
    ]
}


def test_eligible_keeps_threadable_items_only() -> None:
    assert [i.id for i in eligible(CFG, ITEMS, AUTO_MODES)] == ["a", "b", "c"]
    assert [i.id for i in eligible(CFG, ITEMS, frozenset({"tracker"}))] == ["ph"]


def test_all_pairs_are_same_topic_with_scores() -> None:
    items = eligible(CFG, ITEMS, AUTO_MODES)
    pairs = all_pairs(items, embed_items(items, HashingEmbedder()))
    assert {(p.a.id, p.b.id) for p in pairs} == {("a", "b"), ("a", "c"), ("b", "c")}
    ab = next(p for p in pairs if (p.a.id, p.b.id) == ("a", "b"))
    assert ab.shared_entities == [
        "berlin",
        "spd",
    ]  # "Germany" leads title a; "election" is lowercase
    assert ab.score == round(ab.cosine + ab.boost, 4)
    assert ab.label is None


def pair(n: int, score: float, topic: str = "world") -> Pair:
    side = lambda s: PairSide(s, s, "src", "2026-11-22T00:00:00+00:00")  # noqa: E731
    return Pair(topic, side(f"x{n}"), side(f"y{n}"), score, 0.0, score, [])


def test_sample_spreads_across_bands_and_never_reuses_items() -> None:
    pairs = [
        pair(n, lo + 0.01 * (n % 5))
        for lo, _ in BANDS
        for n in range(int(lo * 1000), int(lo * 1000) + 20)
    ]
    sample = sample_pairs(pairs, 10)
    assert len(sample) == 10
    for lo, hi in BANDS:
        assert sum(lo <= p.score < hi for p in sample) == 2
    ids = [x for p in sample for x in (p.a.id, p.b.id)]
    assert len(ids) == len(set(ids))
    assert sample == sample_pairs(pairs, 10)  # deterministic for a seed


def test_sample_within_range_skips_excluded_items() -> None:
    bands = bands_between(0.65, 0.85, 0.05)
    assert bands == ((0.65, 0.7), (0.7, 0.75), (0.75, 0.8), (0.8, 0.85))
    pairs = [pair(n, 0.60 + 0.01 * n) for n in range(30)]
    sample = sample_pairs(pairs, 8, bands=bands, exclude_items=frozenset({"x10", "y11"}))
    assert all(0.65 <= p.score < 0.85 for p in sample)
    assert {p.a.id for p in sample}.isdisjoint({"x10", "x11"})
    assert len(sample) == 8


def test_sample_round_robins_topics() -> None:
    pairs = [pair(n, 0.80, "world") for n in range(10)] + [
        pair(100 + n, 0.80, "politics") for n in range(10)
    ]
    sample = sample_pairs(pairs, 4 * len(BANDS))
    assert sorted(p.topic_id for p in sample) == ["politics"] * 2 + ["world"] * 2


def test_routing_sample_names_best_and_runner_up() -> None:
    items = eligible(CFG, ITEMS, frozenset({"tracker", "fixed"}))
    embedder = HashingEmbedder()
    routes = routing_sample(CFG, items, embed_items(items, embedder), embedder, per_topic=5)
    assert len(routes) == 1
    r = routes[0]
    assert r.topic_id == "trackers"
    assert {r.thread_id, r.runner_up} == {"phones", "laptops"}
    assert r.score >= r.runner_up_score


def test_cli_writes_unlabeled_json(tmp_path: Path, capsys) -> None:
    save_items(tmp_path / "items", ITEMS.values())
    out = tmp_path / "pairs.json"
    args = ["--state", str(tmp_path), "--config-dir", str(FIXTURE_CONFIG), "--embedder", "hashing"]
    assert main(["pairs", *args, "--n", "30", "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert all(p["label"] is None and p["topic_id"] == "world" for p in data)
    assert "3 eligible items" in capsys.readouterr().out
    assert main(["routing", *args]) == 0


def test_cli_without_items_fails(tmp_path: Path) -> None:
    args = ["--state", str(tmp_path), "--config-dir", str(FIXTURE_CONFIG), "--embedder", "hashing"]
    assert main(["pairs", *args]) == 1


def test_cli_evaluate(tmp_path: Path, capsys) -> None:
    side = {"id": "x", "title": "x", "source_id": "s", "published_at": "2026-11-22"}
    pairs = [
        {"topic_id": "w", "a": side, "b": side, "cosine": c, "label": lab}
        for c, lab in ((0.9, True), (0.85, True), (0.7, False), (0.6, False))
    ]
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps(pairs))
    assert main(["evaluate", "--pairs", str(path)]) == 0
    assert "4 labeled pairs: 2 same thread, 2 different" in capsys.readouterr().out
    path.write_text(json.dumps([pairs[0] | {"label": None}]))
    assert main(["evaluate", "--pairs", str(path)]) == 1
