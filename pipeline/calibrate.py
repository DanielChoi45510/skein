"""Relevance calibration: python -m pipeline.calibrate --state DIR

Scores the items already in a state dir (no fetching) against the current
config, with the bge query instruction off and on, and prints per topic:
score percentiles, how many items each candidate threshold would keep, and the
lowest- and highest-scoring titles. Use it to choose `relevance_threshold`
values and `USE_QUERY_INSTRUCTION`, e.g. after changing sources or topics.

Scores are recomputed with the current topics; thresholds and per-source
`relevance` overrides don't affect them.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np

from .config import load_config
from .config.validate import DEFAULT_CONFIG_DIR
from .process.embed import SentenceTransformerEmbedder
from .process.relevance import assign_topics
from .state import ITEMS_DIR, load_items

CANDIDATE_THRESHOLDS = (0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45)
PERCENTILES = (10, 25, 50, 75, 90)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.calibrate")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    parser.add_argument("--samples", type=int, default=4, help="titles shown per end, per topic")
    args = parser.parse_args(argv)

    cfg = load_config(args.config_dir)
    sources = {s.id: s for s in cfg.sources.sources}
    stored = load_items(args.state / ITEMS_DIR, dt.datetime.now(dt.UTC).date())
    base = [
        i.model_copy(update={"topic_id": None, "relevance": None})
        for i in stored.values()
        if i.source_id in sources and i.hidden_reason != "duplicate"
    ]
    if not base:
        print("No items to score: run the pipeline first.", file=sys.stderr)
        return 1
    print(f"{len(base)} items from {len({i.source_id for i in base})} source(s)\n")

    embedder = SentenceTransformerEmbedder()
    for instruction in (False, True):
        embedder.query_instruction = instruction
        items = [i.model_copy() for i in base]
        assign_topics(items, sources, cfg.topics, embedder)
        label = "WITH query instruction" if instruction else "NO query instruction"
        print(f"=== {label} " + "=" * (70 - len(label)))
        _report(items, args.samples)
    return 0


def _report(items: list, samples: int) -> None:
    by_topic: dict[str, list] = {}
    for i in items:
        by_topic.setdefault(i.topic_id, []).append(i)

    pct = " ".join(f"p{p:<4}" for p in PERCENTILES)
    keep = " ".join(f"≥{t:.2f}" for t in CANDIDATE_THRESHOLDS)
    print(f"{'topic':<16}{'n':>4}  {pct}  | kept at {keep}")
    for topic_id in sorted(by_topic):
        scores = np.array([i.relevance for i in by_topic[topic_id]])
        p = " ".join(f"{np.percentile(scores, q):.2f} " for q in PERCENTILES)
        kept = " ".join(f"{int((scores >= t).sum()):>5}" for t in CANDIDATE_THRESHOLDS)
        print(f"{topic_id:<16}{len(scores):>4}  {p} | kept at {kept}")

    for topic_id in sorted(by_topic):
        ranked = sorted(by_topic[topic_id], key=lambda i: i.relevance)
        print(f"\n  {topic_id}: lowest / highest")
        shown = ranked[:samples] + (["…"] if len(ranked) > 2 * samples else []) + ranked[-samples:]
        seen = set()
        for i in shown:
            if i == "…":
                print("     …")
                continue
            if i.id in seen:
                continue
            seen.add(i.id)
            print(f"    {i.relevance:.2f}  {i.title[:72]:<72}  [{i.source_id}]")
    print()


if __name__ == "__main__":
    sys.exit(main())
