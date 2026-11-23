"""The tuned thread thresholds against the owner-labeled pairs (DESIGN §6.5).

If a change to the entity rules or the constants moves these numbers, rerun
`python -m pipeline.threadpairs evaluate --pairs tests/fixtures/threading/pairs.json`
and update the constants, DESIGN §6.5 and this test together.
"""

from __future__ import annotations

import json

from pipeline.process.threads import DEFAULT
from pipeline.threadpairs import JOIN_CUTS, evaluate, evaluate_joins, grid, pair_score

from ..conftest import FIXTURES

PAIRS = json.loads((FIXTURES / "threading" / "pairs.json").read_text())


def test_labeled_set_shape() -> None:
    assert len(PAIRS) == 50
    assert sum(p["label"] for p in PAIRS) == 31  # 18 at first; 13 relabeled at the subject grain
    assert all(isinstance(p["label"], bool) for p in PAIRS)
    assert all("excerpt" not in p["a"] and "excerpt" not in p["b"] for p in PAIRS)


def test_fallback_on_the_labeled_pairs() -> None:
    m = evaluate(PAIRS, DEFAULT.fallback, DEFAULT)
    assert (m.tp, m.fp, m.fn, m.tn) == (28, 3, 3, 16)


def test_tuned_setting_is_the_best_on_the_grid() -> None:
    best = grid(PAIRS)[0]
    ours = evaluate(PAIRS, DEFAULT.fallback, DEFAULT)
    assert best.cut == DEFAULT.fallback
    assert (ours.f05, ours.accuracy) == (best.f05, best.accuracy)  # boosts 0.01-0.03 tie


def test_high_is_above_every_different_pair() -> None:
    """Rescue and outright attaches rely on T_HIGH being precise."""
    assert max(pair_score(p, DEFAULT) for p in PAIRS if not p["label"]) < DEFAULT.high


def test_low_is_below_every_true_pair() -> None:
    """Phase 3's LLM sees the whole gray zone, so no true pair falls below it."""
    assert min(pair_score(p, DEFAULT) for p in PAIRS if p["label"]) >= DEFAULT.low


def test_entity_boost_earns_its_place() -> None:
    no_boost = max((m for m in grid(PAIRS) if m.boost == 0.0), key=lambda m: (m.f05, m.accuracy))
    assert evaluate(PAIRS, DEFAULT.fallback, DEFAULT).f05 > no_boost.f05


# ───────────────────────────── real joins ─────────────────────────────

JOINS = json.loads((FIXTURES / "threading" / "joins.json").read_text())


def test_joins_set_shape() -> None:
    assert len(JOINS) == 20
    assert sum(j["label"] for j in JOINS) == 18
    assert sum(j["group"] == "multi" for j in JOINS) == 16


def test_grown_cut_is_the_best_for_real_joins_to_grown_threads() -> None:
    """Raising it past 0.80 drops good joins much faster than bad ones.

    The joins were sampled at a 0.80 cut, so they say nothing below it; the
    first-run sweep (DESIGN §6.5) showed chaining there.
    """
    multi = [j for j in JOINS if j["group"] == "multi"]
    m = evaluate_joins(multi, DEFAULT.grown)
    assert (m.tp, m.fp, m.fn, m.tn) == (14, 2, 0, 0)
    for cut in JOIN_CUTS:
        assert evaluate_joins(multi, cut).f05 <= m.f05


def test_real_joins_to_one_item_threads_pass_the_pending_cut() -> None:
    single = [j for j in JOINS if j["group"] == "single"]
    assert all(j["label"] and j["score"] >= DEFAULT.fallback for j in single)
