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
    assert sum(p["label"] for p in PAIRS) == 18
    assert all(isinstance(p["label"], bool) for p in PAIRS)
    assert all("excerpt" not in p["a"] and "excerpt" not in p["b"] for p in PAIRS)


def test_fallback_makes_no_wrong_merges() -> None:
    m = evaluate(PAIRS, DEFAULT.fallback, DEFAULT)
    assert (m.tp, m.fp, m.fn, m.tn) == (13, 0, 5, 32)


def test_tuned_setting_is_the_best_on_the_grid() -> None:
    best = grid(PAIRS)[0]
    assert (best.cut, best.boost) == (DEFAULT.fallback, DEFAULT.entity_boost)


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


def test_fallback_is_the_best_cut_for_real_joins() -> None:
    """Grown threads need no stricter cut: raising it drops good joins much faster than bad."""
    m = evaluate_joins(JOINS, DEFAULT.fallback)
    assert (m.tp, m.fp, m.fn, m.tn) == (18, 2, 0, 0)
    for cut in JOIN_CUTS:
        assert evaluate_joins(JOINS, cut).f05 <= m.f05
