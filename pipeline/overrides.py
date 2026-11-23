"""Owner overrides (DESIGN §5, §10.2 "Overrides"), read at the start of each run.

The owner Worker keeps one document: per-thread settings (title, pinned, muted),
applied on every run, and structural ops (merge, split, move), applied once each
(Phase 2b step 6). This module mirrors its shape (worker/src/overrides.ts) and
fetches it:

- with WORKER_URL and WORKER_PIPELINE_TOKEN set (the pipeline workflow), GET
  {WORKER_URL}/overrides; the token is read-only on the Worker's side;
- on any failure (network, HTTP error, malformed document), or when those env
  vars aren't set (a fork, local runs), the last copy saved in the state dir
  (`overrides.json` on the data branch) is used instead.

The run never fails because of the Worker (CLAUDE.md principle 5). The token is
never logged.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from collections.abc import Mapping
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .fetch.http import user_agent

log = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(15.0, connect=10.0)
MAX_BYTES = 2 * 1024 * 1024


class _Doc(BaseModel):
    # Unknown fields are ignored, so a newer Worker never breaks an older pipeline.
    model_config = ConfigDict(extra="ignore", frozen=True)


class ThreadSettings(_Doc):
    title: str | None = None
    pinned: bool = False
    muted: bool = False


class MergeOp(_Doc):
    id: str
    at: dt.datetime
    type: Literal["merge"]
    from_: str = Field(alias="from")
    into: str


class SplitOp(_Doc):
    id: str
    at: dt.datetime
    type: Literal["split"]
    thread: str
    items: list[str]
    new_id: str


class MoveOp(_Doc):
    id: str
    at: dt.datetime
    type: Literal["move"]
    item: str
    to: str


Op = Annotated[MergeOp | SplitOp | MoveOp, Field(discriminator="type")]


class Overrides(_Doc):
    version: Literal[1] = 1
    updated_at: dt.datetime | None = None
    threads: dict[str, ThreadSettings] = {}
    ops: list[Op] = []

    def settings(self, thread_id: str) -> ThreadSettings:
        return self.threads.get(thread_id) or ThreadSettings()

    def title(self, thread_id: str, default: str) -> str:
        return self.settings(thread_id).title or default

    @property
    def pinned(self) -> frozenset[str]:
        return frozenset(t for t, s in self.threads.items() if s.pinned)

    @property
    def muted(self) -> frozenset[str]:
        return frozenset(t for t, s in self.threads.items() if s.muted)


EMPTY = Overrides()


def fetch_overrides(
    url: str, token: str, *, transport: httpx.BaseTransport | None = None
) -> Overrides | None:
    """GET {url}/overrides; None (logged, without the token) on any failure."""
    endpoint = f"{url.rstrip('/')}/overrides"
    try:
        with httpx.Client(timeout=TIMEOUT, transport=transport) as client:
            res = client.get(
                endpoint,
                headers={"Authorization": f"Bearer {token}", "User-Agent": user_agent()},
            )
        if res.status_code != 200:
            log.warning("overrides: Worker answered HTTP %d; using the saved copy", res.status_code)
            return None
        if len(res.content) > MAX_BYTES:
            log.warning("overrides: response too large; using the saved copy")
            return None
        return Overrides.model_validate_json(res.content)
    except httpx.HTTPError as e:
        log.warning("overrides: Worker unreachable (%s); using the saved copy", type(e).__name__)
    except ValidationError as e:
        log.warning(
            "overrides: malformed document (%d errors); using the saved copy", e.error_count()
        )
    return None


def load_overrides(
    saved: Overrides,
    env: Mapping[str, str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> tuple[Overrides, str]:
    """The overrides for this run and where they came from ("worker", "saved" or "none")."""
    env = os.environ if env is None else env
    url, token = env.get("WORKER_URL", "").strip(), env.get("WORKER_PIPELINE_TOKEN", "").strip()
    if url and token:
        fetched = fetch_overrides(url, token, transport=transport)
        if fetched is not None:
            return fetched, "worker"
    elif url or token:
        log.warning("overrides: WORKER_URL and WORKER_PIPELINE_TOKEN must both be set")
    return saved, "saved" if saved != EMPTY else "none"
