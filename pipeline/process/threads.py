"""Thread assignment (DESIGN §6.5): pure functions on vectors, no I/O.

For a relevant item in a threaded / question topic:

    score = cos(item, thread centroid) + entity boost

Candidates are ranked by score. Then:
- top ≥ high, and top - second ≥ margin  → attach;
- top ≥ low (the gray zone, including ≥ high without a clear margin) → the LLM
  picks among the top 3 or "new thread" (Phase 3). Until then, and whenever the
  LLM is unavailable, `resolve_without_llm` attaches if top ≥ fallback, else new;
- otherwise → a new pending thread.

Tracker and fixed topics route every item to the nearest predefined thread,
whose anchor is the embedding of its config `description` (else its title);
they never create threads.

Rescue: an item just below its relevance threshold (within RESCUE_BAND) is kept
only if its best match is an active thread scoring ≥ high. It never creates a
thread.

Vectors are L2-normalized (see embed.py), so a dot product is the cosine.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from ..config.schema import PREDEFINED_MODES, Source, Topic, TopicsFile
from ..models import Item, Thread, ThreadKind
from .embed import Embedder
from .relevance import passes_threshold, threshold_for

RESCUE_BAND = 0.05  # below the relevance threshold (§6.5 "thread rescue")
PENDING_WINDOW = dt.timedelta(hours=72)  # a pending thread can be matched this long (§5)
CENTROID_MIN_ALPHA = 0.25  # weight of the newest item in the centroid, once a thread has 4+


@dataclass(frozen=True)
class Thresholds:
    """Decision constants (DESIGN §6.5).

    Tuned 2026-11-22 on 50 hand-labeled pairs of real stored items
    (tests/fixtures/threading/pairs.json; `python -m pipeline.threadpairs evaluate`):
    - fallback 0.80 with a 0.02 boost: no wrong merges, 13 of 18 true pairs
      joined (DESIGN's 0.65 merged 20 of 32 different pairs);
    - high 0.82: above the best-scoring different pair (0.79); rescue relies on it;
    - low 0.65: below the worst-scoring true pair (0.70), so the Phase 3 LLM
      sees every borderline case;
    - margin: not measurable on pairs (one candidate each); DESIGN's 0.05 kept.
    """

    high: float = 0.82
    low: float = 0.65
    fallback: float = 0.80  # gray zone without the LLM
    margin: float = 0.05  # top - second needed to attach outright at ≥ high
    entity_boost: float = 0.02  # per shared named entity
    entity_boost_max: float = 0.06


DEFAULT = Thresholds()


# ───────────────────────────── ids and kinds ─────────────────────────────


def new_thread_id(topic_id: str, first_item_id: str) -> str:
    """Deterministic: the same first item in the same topic always names the same thread."""
    digest = hashlib.sha256(f"{topic_id}\n{first_item_id}".encode()).hexdigest()
    return f"t{digest[:12]}"


def predefined_thread_id(topic_id: str, thread_id: str) -> str:
    return f"{topic_id}--{thread_id}"


_KINDS: dict[str, ThreadKind] = {
    "threaded": "story",
    "question": "question",
    "tracker": "tracker",
    "fixed": "fixed",
}


def thread_kind(mode: str) -> ThreadKind:
    return _KINDS[mode]


# ───────────────────────────── named entities ─────────────────────────────

_APOSTROPHES = "'\u2019"  # ASCII and typographic
_TOKEN = re.compile(rf"[A-Za-z0-9][A-Za-z0-9.&{_APOSTROPHES}-]*[A-Za-z0-9]|[A-Za-z0-9]")
_POSSESSIVE = re.compile(rf"[{_APOSTROPHES}]s$")
_BRACKETED = re.compile(r"\[[^\]]*\]")  # "[AINews] ...": a feed's tag, not a name in the story
# Capitalized words that title-case headlines use without naming anything.
_COMMON_WORDS = """
a about after again against all an and are as at be before but by can could
did do does for from has have he her his how if in into is it its just more
most new news no not now of off on or our out over report says said she so
than that the their them then there these they this to too under up us vs
was we what when where which who why will with without would you your
first last next year years week weeks day days month months today
"""
_NOT_ENTITIES = frozenset(_COMMON_WORDS.split())


def entities(title: str) -> frozenset[str]:
    """Rough named entities in a headline, lowercased.

    A token counts if it has a digit and a letter (GPT-5, M4), is an acronym
    (NATO, EU), is mixed-case (OpenAI, iPhone), or is capitalized and not the
    headline's first word (which is capitalized anyway, so a plain "Apple" in
    first place is missed). Common title-case words ("Says", "New") and
    bracketed feed tags ("[AINews]") are dropped.
    """
    out: set[str] = set()
    for pos, raw in enumerate(_TOKEN.findall(_BRACKETED.sub(" ", title))):
        token = _POSSESSIVE.sub("", raw)
        low = token.lower()
        if low in _NOT_ENTITIES or len(token) < 2:
            continue
        has_digit = any(c.isdigit() for c in token)
        has_alpha = any(c.isalpha() for c in token)
        if (
            (has_digit and has_alpha)
            or (token.isupper() and has_alpha)
            or any(c.isupper() for c in token[1:])
            or (token[0].isupper() and pos > 0 and has_alpha)
        ):
            out.add(low)
    return frozenset(out)


def entity_boost(
    item_entities: frozenset[str], thread_entities: frozenset[str], t: Thresholds
) -> float:
    shared = len(item_entities & thread_entities)
    return min(t.entity_boost_max, t.entity_boost * shared)


# ───────────────────────────── candidates and decisions ─────────────────────────────


@dataclass(frozen=True)
class Candidate:
    thread_id: str
    centroid: np.ndarray
    entities: frozenset[str]  # from the titles of the thread's items
    state: str


@dataclass(frozen=True)
class Scored:
    thread_id: str
    similarity: float  # cosine with the centroid
    score: float  # similarity + entity boost


@dataclass(frozen=True)
class Attach:
    thread_id: str
    score: float


@dataclass(frozen=True)
class AskLLM:
    """Gray zone: Phase 3 asks the LLM to pick one of `options` or "new thread"."""

    options: tuple[Scored, ...]  # best first, at most 3


@dataclass(frozen=True)
class New:
    pass


Decision = Attach | AskLLM | New


def is_candidate(thread: Thread, has_centroid: bool, now: dt.datetime) -> bool:
    """Threads an item may join: not archived, and pending ones only within 72 h."""
    if not has_centroid or thread.state == "archived":
        return False
    if thread.state == "pending":
        return now - thread.created_at <= PENDING_WINDOW
    return True


def rank(
    vector: np.ndarray,
    item_entities: frozenset[str],
    candidates: Iterable[Candidate],
    t: Thresholds = DEFAULT,
) -> list[Scored]:
    """Candidates by score, best first (ties: thread id, for determinism)."""
    scored = []
    for c in candidates:
        sim = float(np.dot(vector, c.centroid))
        boost = entity_boost(item_entities, c.entities, t)
        scored.append(Scored(c.thread_id, sim, sim + boost))
    scored.sort(key=lambda s: (-s.score, s.thread_id))
    return scored


def decide(ranked: Sequence[Scored], t: Thresholds = DEFAULT) -> Decision:
    if not ranked:
        return New()
    top = ranked[0]
    second = ranked[1].score if len(ranked) > 1 else float("-inf")
    if top.score >= t.high and top.score - second >= t.margin:
        return Attach(top.thread_id, top.score)
    if top.score >= t.low:
        return AskLLM(tuple(ranked[:3]))
    return New()


def resolve_without_llm(decision: Decision, t: Thresholds = DEFAULT) -> Attach | New:
    """The heuristic for the gray zone when no LLM answer is available."""
    if isinstance(decision, AskLLM):
        top = decision.options[0]
        return Attach(top.thread_id, top.score) if top.score >= t.fallback else New()
    return decision


def rescue(
    ranked: Sequence[Scored], states: Mapping[str, str], t: Thresholds = DEFAULT
) -> Attach | None:
    """For an item just below its threshold: attach only to an active thread at ≥ high.

    The best match must itself be that active thread; an item closer to a
    pending or cooling thread is not rescued.
    """
    if not ranked:
        return None
    top = ranked[0]
    if states.get(top.thread_id) == "active" and top.score >= t.high:
        return Attach(top.thread_id, top.score)
    return None


def update_centroid(centroid: np.ndarray | None, vector: np.ndarray, n_items: int) -> np.ndarray:
    """Recency-weighted average. `n_items` counts the thread's items including this one.

    The newest item weighs 1/n while a thread is young (a plain mean) and at
    least CENTROID_MIN_ALPHA after that, so a thread follows its story as it moves.
    """
    if centroid is None or n_items <= 1:
        out = np.asarray(vector, np.float32)
    else:
        alpha = max(1.0 / n_items, CENTROID_MIN_ALPHA)
        out = (1.0 - alpha) * centroid + alpha * vector
    norm = float(np.linalg.norm(out))
    return (out / norm if norm else out).astype(np.float32)


# ───────────────────────────── tracker and fixed topics ─────────────────────────────


def predefined_anchors(topics: Iterable[Topic], embedder: Embedder) -> dict[str, np.ndarray]:
    """Thread id → anchor vector (config description, else title), for tracker / fixed topics."""
    ids, texts = [], []
    for topic in topics:
        if topic.mode not in PREDEFINED_MODES:
            continue
        for th in topic.threads or []:
            ids.append(predefined_thread_id(topic.id, th.id))
            texts.append(th.description or th.title)
    if not texts:
        return {}
    return dict(zip(ids, embedder.embed(texts, "query"), strict=True))


def route_predefined(vector: np.ndarray, anchors: Mapping[str, np.ndarray]) -> Attach:
    """Nearest anchor. Every item attaches; ties go to the thread listed first."""
    best_id, best = "", float("-inf")
    for thread_id, anchor in anchors.items():
        sim = float(np.dot(vector, anchor))
        if sim > best:
            best_id, best = thread_id, sim
    if not best_id:
        raise ValueError("no predefined threads to route to")
    return Attach(best_id, best)


# ───────────────────────────── which items are threaded ─────────────────────────────


def in_rescue_band(item: Item, sources: Mapping[str, Source], topics: TopicsFile) -> bool:
    """Below every carrying source's threshold, but within RESCUE_BAND of one of them."""
    if item.relevance is None or passes_threshold(item, sources, topics):
        return False
    topic = next((t for t in topics.topics if t.id == item.topic_id), None)
    if topic is None:
        return False
    for source_id in (item.source_id, *item.also_covered_by):
        source = sources.get(source_id)
        if (
            source is not None
            and item.relevance >= threshold_for(source, topic, topics) - RESCUE_BAND
        ):
            return True
    return False
