"""One pipeline run. Phase 1 so far:

fetch → normalize → exact dedupe → embed → near-dup → relevance → save state → rank + export

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
from .process.dedupe import NEAR_DUP_WINDOW, mark_near_duplicates, merge_exact
from .process.embed import Embedder, SentenceTransformerEmbedder
from .process.normalize import normalize
from .process.relevance import assign_topics
from .state import State

log = logging.getLogger(__name__)


@dataclass
class RunReport:
    outcomes: dict[str, FetchOutcome] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    new_item_ids: list[str] = field(default_factory=list)

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
) -> RunReport:
    """Run the pipeline. Raises ConfigError if the config is invalid.

    `embedder` defaults to the real model, loaded only when there are new items.
    With `out_dir`, the site's feed JSON is written there (out_dir/feed/...).
    """
    cfg = load_config(config_dir)
    now = now or dt.datetime.now(dt.UTC)
    state = State(state_dir, now)
    report = RunReport()

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

    if report.new_item_ids:
        embedder = embedder or SentenceTransformerEmbedder()
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

        assign_topics([i for i in new_items if i.visible], sources, cfg.topics, embedder)
        hidden = sum(1 for i in new_items if i.hidden_reason == "below_threshold")
        log.info("%d near-duplicate(s), %d below relevance threshold", len(dups), hidden)

    state.save()
    if out_dir is not None:
        index = export_feed(out_dir, cfg, state.items.values(), state.health, now)
        shown = sum(t.visible_count for g in index.groups for t in g.topics)
        log.info("exported %d visible item(s) to %s", shown, out_dir / "feed")
    return report
