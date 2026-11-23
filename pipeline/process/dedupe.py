"""Deduplication (DESIGN §6.3).

1. Exact: items share an id (hash of the canonical URL). Across runs that makes
   the pipeline idempotent; across sources the extra source is recorded in
   `also_covered_by` (a corroboration signal for ranking) and the higher-weight
   source keeps the item.
2. Near-duplicate: title vectors with cosine ≥ 0.92, published within 48 h of
   each other. The higher-weight item stays visible (ties: the one stored first);
   the other is kept with `duplicate_of` + `hidden_reason: duplicate`, so a
   rerun recognizes it by id instead of re-deciding.

Both functions update `store` (id → Item) in place.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping

import numpy as np

from ..models import Item

NEAR_DUP_THRESHOLD = 0.92
NEAR_DUP_WINDOW = dt.timedelta(hours=48)


def merge_exact(
    store: dict[str, Item], candidates: Iterable[Item], weights: Mapping[str, float]
) -> list[str]:
    """Add candidates to the store; returns the ids that are new."""
    added: list[str] = []
    for item in candidates:
        existing = store.get(item.id)
        if existing is None:
            store[item.id] = item
            added.append(item.id)
            continue
        if item.source_id == existing.source_id:
            # Already known: a no-op that keeps reruns idempotent, except that an item
            # stored before its feed offered an image (or before images were captured)
            # picks the image up once.
            if existing.image_url is None and item.image_url is not None:
                existing.image_url = item.image_url
            continue
        if item.source_id in existing.also_covered_by:
            continue  # already known: no-op, which keeps reruns idempotent
        if existing.duplicate_of and (kept := store.get(existing.duplicate_of)):
            # Hidden near-duplicate: the corroboration belongs to the item that is shown.
            existing.also_covered_by = _add(existing.also_covered_by, item.source_id)
            if item.source_id != kept.source_id:
                kept.also_covered_by = _add(kept.also_covered_by, item.source_id)
        elif weights.get(item.source_id, 1.0) > weights.get(existing.source_id, 1.0):
            # The more trusted source takes over the item; the other becomes corroboration.
            existing.also_covered_by = _add(existing.also_covered_by, existing.source_id)
            existing.source_id = item.source_id
            existing.url, existing.title, existing.excerpt = item.url, item.title, item.excerpt
            existing.image_url = item.image_url  # the image belongs to the source shown
            existing.extra = item.extra
        else:
            existing.also_covered_by = _add(existing.also_covered_by, item.source_id)
    return added


def mark_near_duplicates(
    store: dict[str, Item],
    new_ids: Iterable[str],
    vectors: Mapping[str, np.ndarray],
    weights: Mapping[str, float],
    *,
    threshold: float = NEAR_DUP_THRESHOLD,
    window: dt.timedelta = NEAR_DUP_WINDOW,
) -> list[tuple[str, str]]:
    """Hide near-duplicate items. Returns (hidden id, kept id) pairs in decision order.

    Each new item is compared with every visible item that has a vector and was
    published within `window` of it (other new items included, in order).
    """
    decisions: list[tuple[str, str]] = []
    order = list(new_ids)
    pending = set(order)  # new items not yet processed are not "there first"
    for new_id in order:
        pending.discard(new_id)
        new = store[new_id]
        if not new.visible or new_id not in vectors:
            continue
        pool = [
            other
            for other in store.values()
            if other.id != new_id
            and other.id not in pending
            and other.visible
            and other.id in vectors
            and abs(other.published_at - new.published_at) <= window
        ]
        if not pool:
            continue
        sims = _cosine(vectors[new_id], np.stack([vectors[o.id] for o in pool]))
        best = int(np.argmax(sims))
        if sims[best] < threshold:
            continue
        match = pool[best]
        if weights.get(new.source_id, 1.0) > weights.get(match.source_id, 1.0):
            keep, hide = new, match
        else:
            keep, hide = match, new  # ties keep the item that was there first
        _hide_as_duplicate(store, hide, keep)
        decisions.append((hide.id, keep.id))
    return decisions


def _hide_as_duplicate(store: dict[str, Item], hide: Item, keep: Item) -> None:
    hide.duplicate_of = keep.id
    hide.hidden_reason = "duplicate"
    for source_id in (hide.source_id, *hide.also_covered_by):
        if source_id != keep.source_id:
            keep.also_covered_by = _add(keep.also_covered_by, source_id)
    # Anything that pointed at the hidden item now points at the one kept.
    for other in store.values():
        if other.duplicate_of == hide.id:
            other.duplicate_of = keep.id


def _cosine(v: np.ndarray, m: np.ndarray) -> np.ndarray:
    denom = np.linalg.norm(m, axis=1) * np.linalg.norm(v)
    denom[denom == 0] = 1.0
    return (m @ v) / denom


def _add(values: list[str], value: str) -> list[str]:
    return sorted({*values, value})
