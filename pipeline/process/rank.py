"""Ranking (DESIGN §6.6).

    importance = relevance * source_weight * (1 + 0.3*ln(1 + corroborating sources)) * freshness

freshness halves every FRESHNESS_HALF_LIFE_HOURS. Importance depends on the
current time, so it's computed at export and never stored: storing it would
rewrite every item partition on every run.
"""

from __future__ import annotations

import datetime as dt
import math

from ..models import Item

CORROBORATION_FACTOR = 0.3
FRESHNESS_HALF_LIFE_HOURS = 36.0


def freshness(published_at: dt.datetime, now: dt.datetime) -> float:
    age_hours = max(0.0, (now - published_at).total_seconds() / 3600)
    return 0.5 ** (age_hours / FRESHNESS_HALF_LIFE_HOURS)


def importance(item: Item, source_weight: float, now: dt.datetime) -> float:
    relevance = item.relevance if item.relevance is not None else 0.0
    corroboration = 1 + CORROBORATION_FACTOR * math.log1p(len(item.also_covered_by))
    return relevance * source_weight * corroboration * freshness(item.published_at, now)
