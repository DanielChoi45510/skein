"""One pipeline run:

fetch → normalize → exact dedupe → embed → near-dup → relevance scores → threads
      → save state → export (thresholds, ranking, caps)

The embedding model is loaded at most once, and only when something needs a
vector: new items, stored items still to be threaded, or tracker / fixed anchors.

A source that fails is recorded in source health and skipped; it never fails the
run. Everything is written to the state dir once, at the end (see state.py).
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .config import load_config
from .config.validate import DEFAULT_CONFIG_DIR
from .export import export_feed
from .fetch import FeedParseError, FetchError, FetchOutcome, HttpFetcher, fetch_source
from .models import RawEntry, SourceHealth
from .overrides import load_overrides
from .process.dedupe import NEAR_DUP_WINDOW, mark_near_duplicates, merge_exact
from .process.embed import Embedder, SentenceTransformerEmbedder
from .process.normalize import normalize
from .process.relevance import assign_topics
from .process.thread_assign import ThreadReport, assign_threads
from .process.threads import DEFAULT, Thresholds
from .state import State

log = logging.getLogger(__name__)


@dataclass
class RunReport:
    outcomes: dict[str, FetchOutcome] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    new_item_ids: list[str] = field(default_factory=list)
    threads: ThreadReport = field(default_factory=ThreadReport)

    @property
    def entries(self) -> list[RawEntry]:
        return [e for o in self.outcomes.values() for e in o.entries]


def run(
    state_dir: Path,
    *,
    out_dir: Path | None = None,
    config_dir: Path = DEFAULT_CONFIG_DIR,
    now: dt.datetime | None = None,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    embedder: Embedder | None = None,
    thresholds: Thresholds = DEFAULT,
) -> RunReport:
    """Run the pipeline. Raises ConfigError if the config is invalid.

    `embedder` defaults to the real model, loaded only when there are new items.
    With `out_dir`, the site's feed JSON is written there (out_dir/feed/...).
    """
    cfg = load_config(config_dir)
    now = now or dt.datetime.now(dt.UTC)
    state = State(state_dir, now)
    report = RunReport()
    # Owner overrides first (DESIGN §10.2): the Worker's copy, else the last saved one.
    state.overrides, origin = load_overrides(state.overrides)
    o = state.overrides
    log.info(
        "overrides (%s): %d renamed, %d pinned, %d muted, %d op(s)",
        origin, sum(1 for s in o.threads.values() if s.title), len(o.pinned), len(o.muted),
        len(o.ops),
    )  # fmt: skip

    enabled = [s for s in cfg.sources.sources if s.status != "disabled"]
    with HttpFetcher(state.http_cache, transport=transport, sleep=sleep) as http:
        for source in enabled:
            health = state.health.setdefault(source.id, SourceHealth())
            health.last_attempt_at = now
            try:
                outcome = fetch_source(source, http)
            except (FetchError, FeedParseError) as e:
                message = str(e)
            except Exception as e:  # a bug in one parser must never fail the whole run
                message = f"unexpected {type(e).__name__}: {e}"
                log.exception("%s: unexpected error", source.id)
            else:
                report.outcomes[source.id] = outcome
                health.last_status = outcome.status
                health.last_success_at = now
                health.consecutive_failures = 0
                if outcome.status == "ok":
                    health.last_item_count = len(outcome.entries)
                    health.feed_title = outcome.feed_title
                log.info("%s: %s, %d entries", source.id, outcome.status, len(outcome.entries))
                continue

            report.errors[source.id] = message
            health.last_status = "error"
            health.last_error, health.last_error_at = message, now
            health.consecutive_failures += 1
            log.warning("%s: error: %s", source.id, message)

    sources = {s.id: s for s in cfg.sources.sources}
    weights = {s.id: s.weight for s in cfg.sources.sources}
    candidates = normalize(report.entries, sources, cfg.topics, now)
    report.new_item_ids = merge_exact(state.items, candidates, weights)
    log.info("%d new item(s) from %d entries", len(report.new_item_ids), len(report.entries))

    model: list[Embedder] = [embedder] if embedder else []

    def get_embedder() -> Embedder:
        if not model:
            model.append(SentenceTransformerEmbedder())
        return model[0]

    vectors = {}
    if report.new_item_ids:
        embedder = get_embedder()
        new_items = [state.items[i] for i in report.new_item_ids]

        # Near-duplicates: compare titles with every visible item that could be in range.
        oldest = min(i.published_at for i in new_items) - NEAR_DUP_WINDOW
        pool = [i for i in state.items.values() if i.visible and i.published_at >= oldest]
        vectors = dict(
            zip(
                [i.id for i in pool],
                embedder.embed([i.title for i in pool], "passage"),
                strict=True,
            )
        )
        dups = mark_near_duplicates(state.items, report.new_item_ids, vectors, weights)

        vectors = assign_topics([i for i in new_items if i.visible], sources, cfg.topics, embedder)
        log.info("%d near-duplicate(s)", len(dups))

    report.threads = assign_threads(
        state.items,
        state.threads,
        state.centroids,
        cfg,
        now,
        new_ids=set(report.new_item_ids),
        vectors=vectors,
        get_embedder=get_embedder,
        t=thresholds,
        overrides=state.overrides,
        applied_ops=state.applied_ops,
    )
    t = report.threads
    if t.ops_applied or t.ops_skipped:
        log.info("overrides: %d op(s) applied, %d skipped", t.ops_applied, t.ops_skipped)
    log.info(
        "threads: %d item(s) assigned (%d joined, %d new pending, %d tracker/fixed, "
        "%d rescued, %d backfilled); %d thread(s) pruned",
        t.assigned, t.attached, t.created, t.predefined, t.rescued, t.backfilled, t.pruned,
    )  # fmt: skip

    state.save()
    if out_dir is not None:
        index = export_feed(
            out_dir,
            cfg,
            state.items.values(),
            state.health,
            now,
            threads=state.threads,
            overrides=state.overrides,
        )
        shown = sum(t.visible_count for g in index.groups for t in g.topics)
        log.info("exported %d visible item(s) to %s", shown, out_dir / "feed")
    return report
