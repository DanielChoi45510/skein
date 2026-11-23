"""Labeled-set builder for thread thresholds (DESIGN §6.5): a dev tool, like calibrate.

    python -m pipeline.threadpairs pairs   --state DIR [--n 30] [--out pairs.json]
                                           [--range LO HI [--step 0.05]] [--exclude earlier.json]
    python -m pipeline.threadpairs routing --state DIR [--per-topic 10]
    python -m pipeline.threadpairs evaluate --pairs tests/fixtures/threading/pairs.json

`pairs` embeds the stored items that would be threaded (visible, in a threaded
or question topic, passing the relevance threshold) and samples same-topic
pairs evenly across similarity bands, so the labeled set covers both sides of
every threshold. A pair's score is cosine + entity boost, as in assignment.
With `--out`, the sample is written as JSON with `label: null` for a human to
fill in (true = same thread). Item-item similarity stands in for item-centroid
similarity: for a one-item pending thread they are the same.

`evaluate` needs no model: it scores labeled pairs from their recorded cosine
plus the current entity boost, and grid-searches the attach threshold and the
boost. Without the LLM a one-item thread is joined iff score ≥ `fallback`
(a single candidate always has a clear margin), so that is the cut it tunes.
It ranks settings by F0.5: a wrong merge muddles a thread, while a missed one
only leaves an item as its own pending thread, so precision weighs more.

`routing` shows, for tracker and fixed topics, which predefined thread each
sampled item goes to, with the runner-up, to judge whether title anchors work.

Reads the state dir only; never writes to it. Needs the `[embed]` extra unless
`--embedder hashing` (tests only: its scores are meaningless).
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import random
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .config import load_config
from .config.schema import PREDEFINED_MODES, Topic
from .config.validate import DEFAULT_CONFIG_DIR, Config
from .models import Item
from .process.embed import Embedder, HashingEmbedder, SentenceTransformerEmbedder
from .process.normalize import excluded_by_title
from .process.relevance import item_text, passes_threshold
from .process.threads import DEFAULT, Thresholds, entities, entity_boost, predefined_anchors
from .state import ITEMS_DIR, load_items

BANDS = ((0.45, 0.55), (0.55, 0.65), (0.65, 0.75), (0.75, 0.85), (0.85, 0.95))
AUTO_MODES = frozenset({"threaded", "question"})


@dataclass(frozen=True)
class PairSide:
    id: str
    title: str
    source_id: str
    published_at: str


@dataclass(frozen=True)
class Pair:
    topic_id: str
    a: PairSide
    b: PairSide
    cosine: float
    boost: float
    score: float  # cosine + boost
    shared_entities: list[str]
    label: bool | None = None  # true = the two belong in the same thread


def eligible(cfg: Config, items: Mapping[str, Item], modes: frozenset[str]) -> list[Item]:
    """Stored items that thread assignment would see, for topics in `modes`."""
    enabled = {s.id: s for s in cfg.sources.sources if s.status != "disabled"}
    topic_modes = {t.id: t.mode for t in cfg.topics.topics}
    out = [
        i
        for i in items.values()
        if i.visible
        and topic_modes.get(i.topic_id or "") in modes
        and any(sid in enabled for sid in (i.source_id, *i.also_covered_by))
        and not excluded_by_title(i, enabled)
        and passes_threshold(i, enabled, cfg.topics)
    ]
    return sorted(out, key=lambda i: i.id)


def embed_items(items: Sequence[Item], embedder: Embedder) -> dict[str, np.ndarray]:
    if not items:
        return {}
    vectors = embedder.embed([item_text(i) for i in items], "passage")
    return {i.id: v for i, v in zip(items, vectors, strict=True)}


def _side(item: Item) -> PairSide:
    return PairSide(item.id, item.title, item.source_id, item.published_at.isoformat())


def all_pairs(items: Sequence[Item], vectors: Mapping[str, np.ndarray]) -> list[Pair]:
    by_topic: dict[str, list[Item]] = {}
    for i in items:
        by_topic.setdefault(i.topic_id or "", []).append(i)
    pairs = []
    for topic_id in sorted(by_topic):
        for a, b in itertools.combinations(by_topic[topic_id], 2):
            ea, eb = entities(a.title), entities(b.title)
            cos = float(np.dot(vectors[a.id], vectors[b.id]))
            boost = entity_boost(ea, eb, DEFAULT)
            pairs.append(
                Pair(
                    topic_id=topic_id,
                    a=_side(a),
                    b=_side(b),
                    cosine=round(cos, 4),
                    boost=round(boost, 4),
                    score=round(cos + boost, 4),
                    shared_entities=sorted(ea & eb),
                )
            )
    return pairs


def bands_between(lo: float, hi: float, step: float) -> tuple[tuple[float, float], ...]:
    """[lo, hi) cut into `step`-wide bands, e.g. 0.65-0.85 by 0.05 → four bands."""
    count = round((hi - lo) / step)
    return tuple((round(lo + k * step, 4), round(lo + (k + 1) * step, 4)) for k in range(count))


def sample_pairs(
    pairs: Sequence[Pair],
    n: int,
    seed: int = 0,
    *,
    bands: Sequence[tuple[float, float]] = BANDS,
    exclude_items: frozenset[str] = frozenset(),
) -> list[Pair]:
    """About n/len(bands) pairs per score band, spread round-robin across topics.

    No item appears twice (nor any in `exclude_items`, e.g. an earlier batch's),
    so one prolific story can't fill the sample.
    """
    rng = random.Random(seed)
    per_band = max(1, n // len(bands))
    used: set[str] = set(exclude_items)
    picked: list[Pair] = []
    for lo, hi in bands:
        by_topic: dict[str, list[Pair]] = {}
        for p in pairs:
            if lo <= p.score < hi:
                by_topic.setdefault(p.topic_id, []).append(p)
        for group in by_topic.values():
            rng.shuffle(group)
        queues = [by_topic[t] for t in sorted(by_topic)]
        band: list[Pair] = []
        while len(band) < per_band and any(queues):
            for q in queues:
                while q and (q[0].a.id in used or q[0].b.id in used):
                    q.pop(0)
                if q and len(band) < per_band:
                    p = q.pop(0)
                    band.append(p)
                    used.update((p.a.id, p.b.id))
        picked += sorted(band, key=lambda p: p.score)
    return picked


@dataclass(frozen=True)
class Route:
    topic_id: str
    item_id: str
    title: str
    thread_id: str
    score: float
    runner_up: str
    runner_up_score: float


def routing_sample(
    cfg: Config,
    items: Sequence[Item],
    vectors: Mapping[str, np.ndarray],
    embedder: Embedder,
    per_topic: int,
    seed: int = 0,
) -> list[Route]:
    rng = random.Random(seed)
    topics: dict[str, Topic] = {t.id: t for t in cfg.topics.topics if t.mode in PREDEFINED_MODES}
    anchors = predefined_anchors(topics.values(), embedder)
    routes = []
    for topic_id in sorted(topics):
        own = {k: v for k, v in anchors.items() if k.startswith(f"{topic_id}--")}
        pool = [i for i in items if i.topic_id == topic_id]
        for item in rng.sample(pool, min(per_topic, len(pool))):
            scored = sorted(
                ((float(np.dot(vectors[item.id], a)), tid) for tid, a in own.items()),
                key=lambda st: -st[0],
            )
            best, best_id = scored[0]
            second, second_id = scored[1] if len(scored) > 1 else (float("nan"), "")
            prefix = f"{topic_id}--"
            routes.append(
                Route(
                    topic_id,
                    item.id,
                    item.title,
                    best_id.removeprefix(prefix),
                    round(best, 4),
                    second_id.removeprefix(prefix),
                    round(second, 4),
                )
            )
    return routes


# ───────────────────────────── evaluate ─────────────────────────────

BOOSTS = (0.0, 0.01, 0.02, 0.03)  # per shared entity; capped at 3x
CUTS = tuple(round(0.60 + 0.01 * k, 2) for k in range(26))  # 0.60 … 0.85


def pair_score(pair: Mapping, t: Thresholds) -> float:
    """Recorded cosine + entity boost recomputed from the titles (so entity rules can change)."""
    ea, eb = entities(pair["a"]["title"]), entities(pair["b"]["title"])
    return float(pair["cosine"]) + entity_boost(ea, eb, t)


@dataclass(frozen=True)
class Metrics:
    cut: float
    boost: float
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / (self.tp + self.fp + self.fn + self.tn)

    @property
    def f05(self) -> float:
        p, r = self.precision, self.recall
        return 1.25 * p * r / (0.25 * p + r) if p + r else 0.0


def evaluate(pairs: Sequence[Mapping], cut: float, t: Thresholds) -> Metrics:
    tp = fp = fn = tn = 0
    for p in pairs:
        joined = pair_score(p, t) >= cut
        if p["label"]:
            tp, fn = tp + joined, fn + (not joined)
        else:
            fp, tn = fp + joined, tn + (not joined)
    return Metrics(cut, t.entity_boost, tp, fp, fn, tn)


def grid(pairs: Sequence[Mapping]) -> list[Metrics]:
    """Every (boost, cut) setting, best first: F0.5, then accuracy, then the higher cut."""
    out = [
        evaluate(pairs, cut, Thresholds(entity_boost=b, entity_boost_max=3 * b))
        for b in BOOSTS
        for cut in CUTS
    ]
    return sorted(out, key=lambda m: (-m.f05, -m.accuracy, -m.cut, m.boost))


def _print_evaluation(pairs: Sequence[Mapping]) -> None:
    same = sum(1 for p in pairs if p["label"])
    print(f"{len(pairs)} labeled pairs: {same} same thread, {len(pairs) - same} different\n")
    print(f"{'boost':>5} {'cut':>5}  {'prec':>5} {'recall':>6} {'acc':>5} {'F0.5':>5}  tp fp fn tn")
    for m in grid(pairs)[:12]:
        print(
            f"{m.boost:>5.2f} {m.cut:>5.2f}  {m.precision:>5.2f} {m.recall:>6.2f} "
            f"{m.accuracy:>5.2f} {m.f05:>5.2f}  {m.tp:>2} {m.fp:>2} {m.fn:>2} {m.tn:>2}"
        )


def _embedder(name: str) -> Embedder:
    return HashingEmbedder() if name == "hashing" else SentenceTransformerEmbedder()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.threadpairs")
    sub = parser.add_subparsers(dest="command", required=True)
    p_eval = sub.add_parser("evaluate")
    p_eval.add_argument("--pairs", type=Path, required=True, help="labeled pairs JSON")
    for name in ("pairs", "routing"):
        p = sub.add_parser(name)
        p.add_argument("--state", type=Path, required=True)
        p.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
        p.add_argument("--embedder", choices=["model", "hashing"], default="model")
        p.add_argument("--seed", type=int, default=0)
    sub.choices["pairs"].add_argument("--n", type=int, default=30)
    sub.choices["pairs"].add_argument("--out", type=Path, help="write the sample as JSON")
    sub.choices["pairs"].add_argument(
        "--range", nargs=2, type=float, metavar=("LO", "HI"), help="sample only this score range"
    )
    sub.choices["pairs"].add_argument(
        "--step", type=float, default=0.05, help="band width for --range"
    )
    sub.choices["pairs"].add_argument(
        "--exclude",
        type=Path,
        action="append",
        default=[],
        help="earlier sample JSON whose items are not reused (repeatable)",
    )
    sub.choices["routing"].add_argument("--per-topic", type=int, default=10)
    args = parser.parse_args(argv)

    if args.command == "evaluate":
        pairs = json.loads(args.pairs.read_text())
        if any(p.get("label") is None for p in pairs):
            print("Every pair needs a true/false label.", file=sys.stderr)
            return 1
        _print_evaluation(pairs)
        return 0

    cfg = load_config(args.config_dir)
    stored = load_items(args.state / ITEMS_DIR, dt.datetime.now(dt.UTC).date())
    modes = AUTO_MODES if args.command == "pairs" else PREDEFINED_MODES
    items = eligible(cfg, stored, modes)
    if not items:
        print("No eligible items: run the pipeline first.", file=sys.stderr)
        return 1
    embedder = _embedder(args.embedder)
    vectors = embed_items(items, embedder)

    if args.command == "routing":
        for r in routing_sample(cfg, items, vectors, embedder, args.per_topic, args.seed):
            print(
                f"{r.topic_id:<14} {r.thread_id:<13} {r.score:.2f}  "
                f"(next {r.runner_up} {r.runner_up_score:.2f})  {r.title[:80]}"
            )
        return 0

    pairs = all_pairs(items, vectors)
    bands = bands_between(*args.range, args.step) if args.range else BANDS
    exclude = frozenset(
        side["id"]
        for path in args.exclude
        for p in json.loads(path.read_text())
        for side in (p["a"], p["b"])
    )
    sample = sample_pairs(pairs, args.n, args.seed, bands=bands, exclude_items=exclude)
    print(f"{len(items)} eligible items, {len(pairs)} same-topic pairs, {len(sample)} sampled\n")
    for n, p in enumerate(sample, 1):
        shared = f"  shared: {', '.join(p.shared_entities)}" if p.shared_entities else ""
        print(f"{n:>2}. [{p.topic_id}] cos {p.cosine:.2f} + {p.boost:.2f} = {p.score:.2f}{shared}")
        print(f"    A: {p.a.title}  [{p.a.source_id}]")
        print(f"    B: {p.b.title}  [{p.b.source_id}]")
    if args.out:
        args.out.write_text(json.dumps([asdict(p) for p in sample], indent=2) + "\n")
        print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
