"""Structural owner overrides (DESIGN §10.2 "Overrides"): merge, split, move.

The Worker records each as a one-shot op with an id. At the start of thread
assignment, every op not yet in `applied` (state `overrides_applied.json`) runs
once, in (at, id) order, and its outcome is recorded: "applied" or
"skipped: <reason>". Skipped ops are never retried: they point at something that
is gone or isn't allowed, and the owner can simply do it again in the app.

- merge from → into: `into` takes all of `from`'s items; `from` is deleted.
- split thread, items → new_id: a new thread with those of the items that are in
  `thread` (and loaded); `thread` keeps the rest.
- move item → to: the item leaves its thread (if any) and joins `to`.

Rules: both threads in the same topic; merge and split only in threaded and
question topics (tracker and fixed topics have only their configured threads, so
there only `move` works); a thread left empty is deleted; a pending thread that
receives items becomes active (the owner chose to group them). Afterwards each
affected automatic thread gets its centroid recomputed as the plain mean of its
loaded items' vectors (embedded again; only these few) and a new keyword title.
Items placed by hand stay put: assignment never re-threads an item that has a
thread.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass

import numpy as np

from ..config.schema import PREDEFINED_MODES, Topic
from ..models import Item, Thread
from ..overrides import MergeOp, MoveOp, Op, SplitOp
from .lifecycle import TitleOf, retitle

log = logging.getLogger(__name__)

Embed = Callable[[list[Item]], Mapping[str, np.ndarray]]


@dataclass
class OpsReport:
    applied: int = 0
    skipped: int = 0


class _Skip(Exception):
    pass


def prune_applied(applied: MutableMapping[str, str], ops: list[Op]) -> None:
    """Forget ids of ops the Worker no longer lists (expired there, so never seen again)."""
    current = {op.id for op in ops}
    for op_id in [k for k in applied if k not in current]:
        del applied[op_id]


def apply_ops(
    ops: list[Op],
    applied: MutableMapping[str, str],
    items: MutableMapping[str, Item],
    threads: MutableMapping[str, Thread],
    centroids: MutableMapping[str, np.ndarray],
    topics: Mapping[str, Topic],
    *,
    embed: Embed,
    title_of: TitleOf,
) -> OpsReport:
    """Apply the ops not yet in `applied`; mutates everything it's given."""
    report = OpsReport()
    touched: set[str] = set()
    for op in sorted(ops, key=lambda o: (o.at, o.id)):
        if op.id in applied:
            continue
        try:
            if isinstance(op, MergeOp):
                touched |= _merge(op, items, threads, centroids, topics)
            elif isinstance(op, SplitOp):
                touched |= _split(op, items, threads, centroids, topics)
            else:
                touched |= _move(op, items, threads, centroids, topics)
        except _Skip as reason:
            applied[op.id] = f"skipped: {reason}"
            report.skipped += 1
            log.warning("override %s (%s) skipped: %s", op.id, op.type, reason)
            continue
        applied[op.id] = "applied"
        report.applied += 1
        log.info("override %s (%s) applied", op.id, op.type)

    affected = [threads[t] for t in sorted(touched) if t in threads]
    _recompute(affected, items, centroids, topics, embed)
    for thread in affected:
        retitle(thread, items, title_of=title_of)
    return report


# ───────────────────────────── ops ─────────────────────────────


def _thread(threads: Mapping[str, Thread], thread_id: str, role: str) -> Thread:
    thread = threads.get(thread_id)
    if thread is None or thread.state == "archived":
        raise _Skip(f"{role} thread {thread_id} is gone")
    return thread


def _automatic(thread: Thread, topics: Mapping[str, Topic], what: str) -> None:
    topic = topics.get(thread.topic_id)
    if topic is None or topic.mode in PREDEFINED_MODES:
        raise _Skip(f"{what} is only possible in threaded and question topics")


def _merge(op: MergeOp, items, threads, centroids, topics) -> set[str]:
    source = _thread(threads, op.from_, "source")
    target = _thread(threads, op.into, "target")
    if source.topic_id != target.topic_id:
        raise _Skip("the threads are in different topics")
    _automatic(source, topics, "merge")
    for item_id in source.item_ids:
        _join(target, item_id, items)
    _delete(source, threads, centroids)
    return {target.id}


def _split(op: SplitOp, items, threads, centroids, topics) -> set[str]:
    source = _thread(threads, op.thread, "source")
    _automatic(source, topics, "split")
    if op.new_id in threads:
        raise _Skip(f"thread {op.new_id} already exists")
    moving = [i for i in op.items if i in source.item_ids and i in items]
    if not moving:
        raise _Skip("none of the items are in the thread")
    created = min(items[i].first_seen_at for i in moving)
    new = Thread(
        id=op.new_id,
        topic_id=source.topic_id,
        kind=source.kind,
        title=source.title,  # retitled below
        state="active",
        created_at=created,
        last_item_at=created,
    )
    threads[new.id] = new
    for item_id in moving:
        source.item_ids.remove(item_id)
        _join(new, item_id, items)
    touched = {new.id}
    if source.item_ids:
        touched.add(source.id)
    else:
        _delete(source, threads, centroids)
    return touched


def _move(op: MoveOp, items, threads, centroids, topics) -> set[str]:
    item = items.get(op.item)
    if item is None:
        raise _Skip(f"item {op.item} is gone")
    target = _thread(threads, op.to, "target")
    if item.topic_id != target.topic_id:
        raise _Skip("the item is in a different topic")
    if item.thread_id == target.id:
        raise _Skip("the item is already in that thread")
    touched = {target.id}
    old = threads.get(item.thread_id or "")
    if old is not None and item.id in old.item_ids:
        old.item_ids.remove(item.id)
        if old.item_ids:
            touched.add(old.id)
        elif old.kind not in ("tracker", "fixed"):
            _delete(old, threads, centroids)
    _join(target, item.id, items)
    item.owner_placed = True  # re-routing a tracker / fixed topic never undoes it (§6.5)
    return touched


def _join(thread: Thread, item_id: str, items: Mapping[str, Item]) -> None:
    if item_id not in thread.item_ids:
        thread.item_ids.append(item_id)
    item = items.get(item_id)
    if item is not None:
        item.thread_id = thread.id
        thread.last_item_at = max(thread.last_item_at, item.published_at)
    if thread.state == "pending":
        thread.state = "active"


def _delete(thread: Thread, threads, centroids) -> None:
    threads.pop(thread.id, None)
    centroids.pop(thread.id, None)


def _recompute(affected: list[Thread], items, centroids, topics, embed: Embed) -> None:
    """Plain mean of each automatic thread's loaded items, embedded in one batch."""
    automatic = [
        t
        for t in affected
        if (topic := topics.get(t.topic_id)) is not None and topic.mode not in PREDEFINED_MODES
    ]
    members = {t.id: [items[i] for i in t.item_ids if i in items] for t in automatic}
    needed = [i for ms in members.values() for i in ms]
    if not needed:
        return
    vectors = embed(needed)
    for thread_id, ms in members.items():
        if not ms:
            continue
        mean = np.mean(np.stack([vectors[i.id] for i in ms]), axis=0)
        norm = float(np.linalg.norm(mean))
        centroids[thread_id] = (mean / norm if norm else mean).astype(np.float32)
