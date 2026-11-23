"""Thread structure for the spine-and-branches view (DESIGN §6.9): pure functions on vectors.

Within a thread, items are grouped into **storylines** by embedding similarity:
average-linkage agglomerative clustering, merging the two closest groups while
their average pairwise cosine is at least `link`. Average linkage (unlike
single linkage / connected components) can't chain unrelated items together
through a run of near neighbours.

- The **spine** is the largest storyline; ties go to the one spanning the most
  time (the most continuous), then the one that started first.
- Every other storyline is a **branch**, anchored to the spine item closest to
  it in meaning and time: the spine item maximizing
  `cos(branch centroid, item) - anchor_day_penalty * |days between them|`,
  measured from the branch's first item.
- Threads with fewer than `min_items` items, or whose largest storyline is a
  single item (no shared storyline at all), are all spine.
- Storylines smaller than `min_branch_items` fold into the spine instead of
  branching.
- Tracker and fixed threads gather a whole subject, so they use the looser
  `link_predefined` and `min_branch_items_predefined` (one-item asides there
  are mostly routing noise, not side stories).

**Related threads** (the spokes) are other threads whose centroid (normalized
mean of their item vectors) has cosine ≥ `related` with this thread's, most
similar first, at most `related_max`. Two predefined threads of the same
tracker / fixed topic are never related: they're that topic's own categories,
already listed side by side (and broadly similar by construction).

Heuristics only: no LLM. Naming branches is Phase 3. Vectors are L2-normalized
(see embed.py), so a dot product is the cosine. Everything is deterministic:
ties break by time, then id.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from ..config.schema import PREDEFINED_MODES, StructureParams, TopicsFile
from ..models import LISTED_STATES, Item, Thread

DAY = 86_400.0


@dataclass(frozen=True)
class Member:
    """One item of a thread, for structure: its id, publication time and vector."""

    id: str
    published_at: dt.datetime
    vector: np.ndarray


@dataclass(frozen=True)
class Branch:
    anchor: str  # spine item id
    items: list[str]  # time order


@dataclass(frozen=True)
class Structure:
    spine: list[str]  # time order
    branches: list[Branch]  # by first item's time


def _order(members: Sequence[Member]) -> list[Member]:
    return sorted(members, key=lambda m: (m.published_at, m.id))


def storylines(vectors: np.ndarray, link: float) -> list[list[int]]:
    """Average-linkage clusters of the rows of `vectors` (indices, each sorted)."""
    n = len(vectors)
    if n == 0:
        return []
    sim = vectors @ vectors.T
    clusters: dict[int, list[int]] = {i: [i] for i in range(n)}
    # total[a, b] = sum of pairwise similarities between clusters a and b
    total = sim.astype(np.float64).copy()
    while len(clusters) > 1:
        keys = sorted(clusters)
        best: tuple[float, int, int] | None = None
        for x, a in enumerate(keys):
            for b in keys[x + 1 :]:
                avg = total[a, b] / (len(clusters[a]) * len(clusters[b]))
                if best is None or avg > best[0] + 1e-12:
                    best = (avg, a, b)
        assert best is not None
        avg, a, b = best
        if avg < link:
            break
        clusters[a] = sorted(clusters[a] + clusters.pop(b))
        total[a, :] += total[b, :]
        total[:, a] += total[:, b]
    return sorted(clusters.values(), key=lambda c: c[0])


def structure(
    members: Sequence[Member], p: StructureParams, *, predefined: bool = False
) -> Structure:
    """Spine and branches of one thread's items."""
    ordered = _order(members)
    ids = [m.id for m in ordered]
    if len(ordered) < p.min_items:
        return Structure(spine=ids, branches=[])
    vectors = np.stack([m.vector for m in ordered])
    groups = storylines(vectors, p.link_predefined if predefined else p.link)

    def span(g: list[int]) -> float:
        return (ordered[g[-1]].published_at - ordered[g[0]].published_at).total_seconds()

    # Largest, then most continuous (longest span), then earliest (indices are time order).
    spine = max(groups, key=lambda g: (len(g), span(g), -g[0]))
    if len(spine) < 2:
        return Structure(spine=ids, branches=[])

    min_branch = p.min_branch_items_predefined if predefined else p.min_branch_items
    folded = sorted(
        spine + [i for g in groups if g is not spine and len(g) < min_branch for i in g]
    )
    branches = []
    for g in groups:
        if g is spine or len(g) < min_branch:
            continue
        centroid = vectors[g].mean(axis=0)
        norm = float(np.linalg.norm(centroid)) or 1.0
        start = ordered[g[0]].published_at

        def score(s: int, centroid: np.ndarray = centroid / norm, start: dt.datetime = start):
            days = abs((ordered[s].published_at - start).total_seconds()) / DAY
            return float(vectors[s] @ centroid) - p.anchor_day_penalty * days

        anchor = max(folded, key=lambda s: (score(s), -s))
        branches.append(Branch(anchor=ids[anchor], items=[ids[i] for i in g]))
    return Structure(spine=[ids[i] for i in folded], branches=branches)


def centroid(vectors: Sequence[np.ndarray]) -> np.ndarray | None:
    if not len(vectors):
        return None
    c = np.mean(np.stack(vectors), axis=0)
    norm = float(np.linalg.norm(c))
    return c / norm if norm else None


def related_threads(
    centroids: Mapping[str, np.ndarray],
    p: StructureParams,
    siblings: Mapping[str, str] | None = None,
) -> dict[str, list[tuple[str, float]]]:
    """For each thread, other threads with centroid cosine ≥ p.related (best first, ≤ related_max).

    `siblings` maps predefined thread ids to their topic: two threads with the
    same entry are never related.
    """
    siblings = siblings or {}
    ids = sorted(centroids)
    if not ids:
        return {}
    matrix = np.stack([centroids[i] for i in ids])
    sim = matrix @ matrix.T
    out: dict[str, list[tuple[str, float]]] = {}
    for x, tid in enumerate(ids):
        pairs = [
            (ids[y], float(sim[x, y]))
            for y in range(len(ids))
            if y != x
            and sim[x, y] >= p.related
            and not (tid in siblings and siblings[tid] == siblings.get(ids[y]))
        ]
        pairs.sort(key=lambda q: (-q[1], q[0]))
        out[tid] = [(other, round(s, 4)) for other, s in pairs[: p.related_max]]
    return out


@dataclass
class Structures:
    """Every listed thread's structure and related threads, for the export."""

    threads: dict[str, Structure] = field(default_factory=dict)
    related: dict[str, list[tuple[str, float]]] = field(default_factory=dict)


def thread_structures(
    items: Mapping[str, Item],
    threads: Mapping[str, Thread],
    topics: TopicsFile,
    vectors_for: Callable[[list[Item]], Mapping[str, np.ndarray]],
    skip: Collection[str] = (),
) -> Structures:
    """Structure and related threads of every listed thread (not pending, archived or in `skip`).

    Uses each thread's visible stored items. `vectors_for` returns a vector per
    item id (title + excerpt, the text thread assignment embeds).
    """
    p = topics.defaults.structure
    predefined_topics = {t.id for t in topics.topics if t.mode in PREDEFINED_MODES}
    listed = sorted(
        (t for t in threads.values() if t.state in LISTED_STATES and t.id not in skip),
        key=lambda t: t.id,
    )
    members = {
        t.id: [items[i] for i in t.item_ids if i in items and items[i].visible] for t in listed
    }
    needed = list({i.id: i for ms in members.values() for i in ms}.values())
    vectors = vectors_for(needed) if needed else {}
    out = Structures()
    centroids: dict[str, np.ndarray] = {}
    for t in listed:
        ms = [Member(i.id, i.published_at, vectors[i.id]) for i in members[t.id] if i.id in vectors]
        if not ms:
            continue
        out.threads[t.id] = structure(ms, p, predefined=t.topic_id in predefined_topics)
        if (c := centroid([m.vector for m in ms])) is not None:
            centroids[t.id] = c
    siblings = {t.id: t.topic_id for t in listed if t.topic_id in predefined_topics}
    out.related = related_threads(centroids, p, siblings)
    return out
