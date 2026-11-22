"""One pipeline run. Phase 1 step (a): fetch only.

fetch → (normalize → dedupe → embed → relevance → rank → export: later steps)

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
from .fetch import FeedParseError, FetchError, FetchOutcome, HttpFetcher, fetch_source
from .models import RawEntry, SourceHealth
from .state import State

log = logging.getLogger(__name__)


@dataclass
class RunReport:
    outcomes: dict[str, FetchOutcome] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def entries(self) -> list[RawEntry]:
        return [e for o in self.outcomes.values() for e in o.entries]


def run(
    state_dir: Path,
    *,
    config_dir: Path = DEFAULT_CONFIG_DIR,
    now: dt.datetime | None = None,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> RunReport:
    """Run the pipeline. Raises ConfigError if the config is invalid."""
    cfg = load_config(config_dir)
    now = now or dt.datetime.now(dt.UTC)
    state = State(state_dir)
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

    state.save()
    return report
