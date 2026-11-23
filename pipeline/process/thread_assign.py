"""Thread assignment for one run (DESIGN §6.5): the glue between threads.py and lifecycle.py.

Each run:
1. Pick the items to assign: visible, in a threaded / question / tracker /
   fixed topic, within the topic's lookback, carried by an enabled source, not
   excluded by title, and without a thread yet. Items that pass the relevance
   threshold are assigned; items just below it (the rescue band) only if they
   are new this run, so a near-miss isn't re-embedded on every run.
   Old unthreaded items that pass (the first run after Phase 2a, or after a
   threshold is lowered) are the backfill: they're embedded again here.
2. In (published_at, id) order, attach each to a thread or start a pending
   one, updating centroids as it goes, so later items can join earlier ones.
3. Advance the lifecycle (§5), retitle changed threads, prune.

Deterministic: the same inputs and `now` give the same threads and centroids.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np

from ..config.schema import PREDEFINED_MODES, THREADED_MODES, Source, Topic
from ..config.validate import Config
from ..models import Item, Thread
from .embed import Embedder
from .lifecycle import advance, prune, retitle
from .normalize import display_title, excluded_by_title
from .relevance import item_text, passes_threshold
from .threads import (
    DEFAULT,
    Attach,
    Candidate,
    Thresholds,
    decide,
    entities,
    in_rescue_band,
    is_candidate,
    new_thread_id,
    predefined_anchors,
    predefined_thread_id,
    rank,
    rescue,
    resolve_without_llm,
    route_predefined,
    thread_kind,
    update_centroid,
)

log = logging.getLogger(__name__)


@dataclass
class ThreadReport:
    assigned: int = 0  # items given a thread this run
    attached: int = 0  # joined an existing automatic thread
    created: int = 0  # started a new pending thread
    predefined: int = 0  # routed to a tracker / fixed thread
    rescued: int = 0  # below threshold, kept by an active thread
    backfilled: int = 0  # old items embedded again to be threaded
    pruned: int = 0


def select(
    items: Mapping[str, Item],
    cfg: Config,
    new_ids: set[str],
    now: dt.datetime,
) -> tuple[list[Item], list[Item]]:
    """(items to assign, rescue candidates), each in (published_at, id) order."""
    enabled = {s.id: s for s in cfg.sources.sources if s.status != "disabled"}
    topics = {t.id: t for t in cfg.topics.topics if t.mode in THREADED_MODES}
    lookback = cfg.topics.defaults.lookback_days
    assign, band = [], []
    for item in items.values():
        topic = topics.get(item.topic_id or "")
        if topic is None or item.thread_id is not None or not item.visible:
            continue
        if item.published_at < now - dt.timedelta(days=topic.lookback_days or lookback):
            continue
        if not any(s in enabled for s in (item.source_id, *item.also_covered_by)):
            continue
        if excluded_by_title(item, enabled):
            continue
        if passes_threshold(item, enabled, cfg.topics):
            assign.append(item)
        elif item.id in new_ids and in_rescue_band(item, enabled, cfg.topics):
            band.append(item)
    order = lambda i: (i.published_at, i.id)  # noqa: E731
    return sorted(assign, key=order), sorted(band, key=order)


def assign_threads(
    items: dict[str, Item],
    threads: dict[str, Thread],
    centroids: dict[str, np.ndarray],
    cfg: Config,
    now: dt.datetime,
    *,
    new_ids: set[str],
    vectors: Mapping[str, np.ndarray],
    get_embedder: Callable[[], Embedder],
    t: Thresholds = DEFAULT,
) -> ThreadReport:
    """Assign threads, then advance the lifecycle. Mutates items, threads and centroids."""
    report = ThreadReport()
    sources: dict[str, Source] = {s.id: s for s in cfg.sources.sources}
    topics: dict[str, Topic] = {tp.id: tp for tp in cfg.topics.topics}

    def title_of(item: Item) -> str:
        return display_title(item, sources)

    to_assign, band = select(items, cfg, new_ids, now)
    pending = to_assign + band
    vecs = dict(vectors)
    missing = [i for i in pending if i.id not in vecs]
    if missing:
        report.backfilled = len(missing)
        log.info("embedding %d stored item(s) to thread them", len(missing))
        out = get_embedder().embed([item_text(i) for i in missing], "passage")
        vecs.update(zip([i.id for i in missing], out, strict=True))
    anchors: dict[str, np.ndarray] = {}
    if any(topics[i.topic_id or ""].mode in PREDEFINED_MODES for i in pending):
        anchors = predefined_anchors(topics.values(), get_embedder())

    ents: dict[str, frozenset[str]] = {}  # thread id → entities of its loaded titles

    def thread_entities(thread: Thread) -> frozenset[str]:
        if thread.id not in ents:
            ents[thread.id] = frozenset().union(
                *(entities(title_of(items[i])) for i in thread.item_ids if i in items)
            )
        return ents[thread.id]

    changed: set[str] = set()

    def attach(item: Item, thread: Thread, score: float, *, centroid: bool) -> None:
        thread.item_ids.append(item.id)
        thread.last_item_at = max(thread.last_item_at, item.published_at)
        if centroid:
            centroids[thread.id] = update_centroid(
                centroids.get(thread.id), vecs[item.id], len(thread.item_ids)
            )
        item.thread_id, item.thread_score = thread.id, round(score, 4)
        ents[thread.id] = thread_entities(thread) | entities(title_of(item))
        changed.add(thread.id)
        report.assigned += 1

    band_ids = {i.id for i in band}
    for item in sorted(pending, key=lambda i: (i.published_at, i.id)):
        topic = topics[item.topic_id or ""]
        vector = vecs[item.id]
        in_band = item.id in band_ids

        if topic.mode in PREDEFINED_MODES:
            own = {k: v for k, v in anchors.items() if k.startswith(f"{topic.id}--")}
            routed = route_predefined(vector, own)
            if in_band and routed.score < t.high:
                continue
            thread = threads.get(routed.thread_id) or _predefined_thread(
                routed.thread_id, topic, item
            )
            threads[thread.id] = thread
            attach(item, thread, routed.score, centroid=False)
            report.predefined += 1
            report.rescued += in_band
            continue

        candidates = [
            Candidate(th.id, centroids[th.id], thread_entities(th), th.state, len(th.item_ids))
            for th in threads.values()
            if th.topic_id == topic.id and is_candidate(th, th.id in centroids, now)
        ]
        ranked = rank(vector, entities(title_of(item)), candidates, t)
        if in_band:
            hit = rescue(ranked, {c.thread_id: c.state for c in candidates}, t)
            if hit is not None:
                attach(item, threads[hit.thread_id], hit.score, centroid=True)
                report.attached += 1
                report.rescued += 1
            continue
        decision = resolve_without_llm(decide(ranked, t), t)
        if isinstance(decision, Attach):
            attach(item, threads[decision.thread_id], decision.score, centroid=True)
            report.attached += 1
        else:
            thread = Thread(
                id=new_thread_id(topic.id, item.id),
                topic_id=topic.id,
                kind=thread_kind(topic.mode),
                title=title_of(item),
                state="pending",
                created_at=item.first_seen_at,
                last_item_at=item.published_at,
            )
            threads[thread.id] = thread
            attach(item, thread, 1.0, centroid=True)
            report.created += 1

    advance(threads, centroids, items, cfg.topics, now, title_of=title_of)
    for thread_id in sorted(changed):
        if thread_id in threads:
            retitle(threads[thread_id], items, title_of=title_of)
    report.pruned = len(prune(threads, centroids, loaded=items.keys()))
    return report


def _predefined_thread(thread_id: str, topic: Topic, first: Item) -> Thread:
    """A tracker / fixed thread's record, created when its first item arrives."""
    config_id = thread_id.removeprefix(f"{topic.id}--")
    spec = next(th for th in topic.threads or [] if th.id == config_id)
    assert predefined_thread_id(topic.id, spec.id) == thread_id
    return Thread(
        id=thread_id,
        topic_id=topic.id,
        kind=thread_kind(topic.mode),
        title=spec.title,
        state="active",
        created_at=first.first_seen_at,
        last_item_at=first.published_at,
    )
