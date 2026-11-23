"""Thread lifecycle and keyword titles (DESIGN §5, §6.5). Pure: mutates what it's given.

    pending ──(2nd item within 72 h, or ≥ 2 corroborating sources)──▶ active
    active ──(cooling_after_days)──▶ cooling ──(dormant_after_days)──▶ dormant
           ──(archive_after_days)──▶ archived

- Timings count from the thread's newest item (`last_item_at`), so a new item
  revives a cooling or dormant thread by itself: its state is recomputed.
- Archived is final: the centroid is dropped and the thread is never matched
  again (§6.5). The owner's merge override (Phase 2b) joins a resurfacing story.
- A pending thread that isn't promoted within 72 h stays pending (its item
  shows as a single item) but drops its centroid: it can no longer be matched.
- A thread the owner pinned (overrides, DESIGN §10.2) never archives: it stops at
  dormant, so it stays listed.
- Tracker and fixed threads (`lifecycle()` is None) are always active and keep
  their config title (renaming one in topics.yaml renames the thread).
- Threads whose topic or predefined thread left the config are archived.

`prune` deletes pending and archived threads none of whose items are loaded
any more (the 30-day item window), which bounds threads.json.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Collection, Mapping, Sequence

import numpy as np

from ..config.schema import THREADED_MODES, Lifecycle, Topic, TopicsFile, lifecycle
from ..models import Item, Thread, ThreadState
from .normalize import clean_title
from .threads import (
    APOSTROPHES,
    COMMON_WORDS,
    PENDING_WINDOW,
    entities,
    predefined_thread_id,
)

PROMOTE_MIN_CORROBORATION = 2  # "very high importance" for a one-item thread (§5)
TITLE_MAX_TERMS = 4
TITLE_SEPARATOR = " · "

TitleOf = Callable[[Item], str]


def _default_title(item: Item) -> str:
    return clean_title(item.title)


# ───────────────────────────── lifecycle ─────────────────────────────


def advance(
    threads: dict[str, Thread],
    centroids: dict[str, np.ndarray],
    items: Mapping[str, Item],
    topics: TopicsFile,
    now: dt.datetime,
    *,
    title_of: TitleOf = _default_title,
    pinned: frozenset[str] = frozenset(),
) -> None:
    """Move every thread to the state its items and `now` call for."""
    by_id = {t.id: t for t in topics.topics}
    for thread in threads.values():
        topic = by_id.get(thread.topic_id)
        if topic is None or topic.mode not in THREADED_MODES or _orphaned(thread, topic):
            _archive(thread, centroids)
            continue
        life = lifecycle(topic, topics.defaults)
        if life is None:  # tracker / fixed: never cools, goes dormant or archives
            thread.state = "active"
            thread.title = next(
                th.title
                for th in topic.threads or []
                if predefined_thread_id(topic.id, th.id) == thread.id
            )
            continue
        if thread.state == "archived":
            centroids.pop(thread.id, None)
            continue
        if thread.state == "pending":
            if _promotable(thread, items, now):
                thread.state = "active"
                retitle(thread, items, title_of=title_of)
            else:
                if now - thread.created_at > PENDING_WINDOW:
                    centroids.pop(thread.id, None)
                continue
        thread.state = _state_for_age(now - thread.last_item_at, life)
        if thread.state == "archived" and thread.id in pinned:
            thread.state = "dormant"
        if thread.state == "archived":
            centroids.pop(thread.id, None)


def _orphaned(thread: Thread, topic: Topic) -> bool:
    """A tracker / fixed thread whose predefined thread was removed from the config."""
    if thread.kind not in ("tracker", "fixed"):
        return False
    return thread.id not in {predefined_thread_id(topic.id, t.id) for t in topic.threads or []}


def _archive(thread: Thread, centroids: dict[str, np.ndarray]) -> None:
    thread.state = "archived"
    centroids.pop(thread.id, None)


def _promotable(thread: Thread, items: Mapping[str, Item], now: dt.datetime) -> bool:
    if now - thread.created_at > PENDING_WINDOW:
        return False
    if len(thread.item_ids) >= 2:  # a 2nd item can only attach within the window
        return True
    first = items.get(thread.item_ids[0]) if thread.item_ids else None
    return first is not None and len(first.also_covered_by) >= PROMOTE_MIN_CORROBORATION


def _state_for_age(age: dt.timedelta, life: Lifecycle) -> ThreadState:
    days = age / dt.timedelta(days=1)
    if days >= life.archive:
        return "archived"
    if days >= life.dormant:
        return "dormant"
    if days >= life.cooling:
        return "cooling"
    return "active"


def prune(
    threads: dict[str, Thread], centroids: dict[str, np.ndarray], loaded: Collection[str]
) -> list[str]:
    """Delete pending / archived threads with no loaded items. Returns the deleted ids."""
    gone = [
        t.id
        for t in threads.values()
        if t.state in ("pending", "archived")
        and t.kind not in ("tracker", "fixed")
        and not any(i in loaded for i in t.item_ids)
    ]
    for thread_id in gone:
        del threads[thread_id]
        centroids.pop(thread_id, None)
    return gone


# ───────────────────────────── titles ─────────────────────────────

_WORD = re.compile(rf"[A-Za-z0-9][A-Za-z0-9.&{APOSTROPHES}-]*[A-Za-z0-9]|[A-Za-z0-9]")
_TRAILING = re.compile(rf"(?:[{APOSTROPHES}]s|[.{APOSTROPHES}-])+$")
# Not useful in a title: function words plus headline filler.
_FILLER_WORDS = """
amid among another any back been being between both by do each even every
few get gets got here into its may might much must near nearly only other
own same should some such take takes than through until very via were while
yet ahead also around despite during per since toward upon opinion latest
exclusive analysis update updates live watch inside really
"""
_STOP = frozenset(COMMON_WORDS.split()) | frozenset(_FILLER_WORDS.split())


def _terms(title: str) -> list[tuple[str, str]]:
    """(key, display form) for the title's content words, in order, once each."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in _WORD.findall(title):
        word = _TRAILING.sub("", raw)
        key = word.lower()
        # Short words only when capitalized ("Xi", "EU") or numeric ("4", "F1").
        has_digit = any(c.isdigit() for c in word)
        too_short = not has_digit and (len(word) == 1 or (len(word) == 2 and word.islower()))
        if too_short or key in _STOP or key in seen:
            continue
        seen.add(key)
        out.append((key, word))
    return out


def keyword_title(titles: Sequence[str], max_terms: int = TITLE_MAX_TERMS) -> str:
    """A short "A · B · C" title from the words the thread's headlines share.

    Terms are chosen by how many headlines use them (named entities first on
    ties, then earlier position), and shown in the order and spelling of the
    newest headline that has them. Without at least two shared terms, the
    newest headline itself is the title. `titles` is oldest first.
    """
    titles = [t for t in titles if t.strip()]
    if not titles:
        return ""
    newest = titles[-1]
    if len(titles) < 2:
        return newest
    df: dict[str, int] = {}
    display: dict[str, str] = {}
    position: dict[str, int] = {}
    ents: set[str] = set()
    for title in titles:  # later titles overwrite: newest spelling wins
        ents |= entities(title)
        for pos, (key, word) in enumerate(_terms(title)):
            df[key] = df.get(key, 0) + 1
            display[key] = word
            position[key] = pos
    shared = [k for k, n in df.items() if n >= 2]
    if len(shared) < 2:
        return newest
    shared.sort(key=lambda k: (-df[k], k not in ents, position[k], k))
    chosen = shared[:max_terms]
    chosen.sort(key=lambda k: position[k])
    return TITLE_SEPARATOR.join(_capitalize(display[k]) for k in chosen)


def _capitalize(word: str) -> str:
    """ "talks" → "Talks"; leaves "iPhone", "GPT-6.2" and "OpenAI" alone."""
    return word[0].upper() + word[1:] if word.islower() else word


def retitle(
    thread: Thread, items: Mapping[str, Item], *, title_of: TitleOf = _default_title
) -> None:
    """Recompute an automatic thread's title from its loaded items (tracker / fixed keep theirs)."""
    if thread.kind in ("tracker", "fixed"):
        return
    loaded = sorted(
        (items[i] for i in thread.item_ids if i in items),
        key=lambda i: (i.published_at, i.id),
    )
    if not loaded:
        return
    if thread.state == "pending":
        thread.title = title_of(loaded[-1])
    else:
        thread.title = keyword_title([title_of(i) for i in loaded]) or thread.title
