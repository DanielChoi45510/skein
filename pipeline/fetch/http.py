"""Shared HTTP client for every source fetcher.

Implements the CLAUDE.md fetcher requirements in one place: timeouts, per-host
rate limiting, retries with backoff (honoring Retry-After), conditional requests
(ETag / Last-Modified), a descriptive User-Agent and a response size cap.
"""

from __future__ import annotations

import email.utils
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

import httpx

from ..models import CacheEntry

VERSION = "0.1"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)
MIN_INTERVAL_PER_HOST = 2.0  # seconds between requests to the same host
MAX_RETRIES = 2
BACKOFF_BASE = 2.0  # seconds; doubles per retry
MAX_RETRY_AFTER = 30.0  # never wait longer than this for one retry
MAX_BODY_BYTES = 5 * 1024 * 1024
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

_REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def user_agent(env: dict[str, str] | None = None) -> str:
    """`Skein/<v> (...)`, with the public repo URL as contact when running in Actions."""
    env = os.environ if env is None else env
    repo = env.get("GITHUB_REPOSITORY", "")
    if _REPO_RE.fullmatch(repo):
        return f"Skein/{VERSION} (personal feed reader; +https://github.com/{repo})"
    return f"Skein/{VERSION} (self-hosted personal feed reader)"


class FetchError(Exception):
    """A source could not be fetched. Recorded in source health; never fails the run."""


@dataclass(frozen=True)
class FetchResult:
    status: Literal["ok", "unchanged"]
    content: bytes = b""


class HttpFetcher:
    def __init__(
        self,
        cache: dict[str, CacheEntry],
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_interval: float = MIN_INTERVAL_PER_HOST,
        max_retries: int = MAX_RETRIES,
    ):
        self.cache = cache  # mutated in place; saved by the caller with the rest of the state
        self._sleep = sleep
        self._clock = clock
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._last_request: dict[str, float] = {}
        self.client = httpx.Client(
            transport=transport,
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": user_agent()},
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> HttpFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get(self, url: str, *, accept: str | None = None) -> FetchResult:
        headers = {}
        if accept:
            headers["Accept"] = accept
        if cached := self.cache.get(url):
            if cached.etag:
                headers["If-None-Match"] = cached.etag
            if cached.last_modified:
                headers["If-Modified-Since"] = cached.last_modified

        attempt = 0
        while True:
            self._wait_for_host(url)
            try:
                status, resp_headers, body = self._request(url, headers)
            except httpx.TimeoutException as e:
                error, retry_after = f"timeout ({type(e).__name__})", None
            except httpx.TransportError as e:
                error, retry_after = f"network error ({type(e).__name__})", None
            else:
                if status == 304:
                    return FetchResult("unchanged")
                if 200 <= status < 300:
                    self._remember_validators(url, resp_headers)
                    return FetchResult("ok", body)
                if status not in RETRY_STATUSES:
                    raise FetchError(f"HTTP {status}")
                error, retry_after = f"HTTP {status}", _parse_retry_after(resp_headers)

            if attempt >= self._max_retries:
                raise FetchError(f"{error} after {attempt + 1} attempts")
            delay = retry_after if retry_after is not None else BACKOFF_BASE * 2**attempt
            self._sleep(min(delay, MAX_RETRY_AFTER))
            attempt += 1

    def _request(self, url: str, headers: dict[str, str]) -> tuple[int, httpx.Headers, bytes]:
        with self.client.stream("GET", url, headers=headers) as resp:
            if not 200 <= resp.status_code < 300:
                return resp.status_code, resp.headers, b""
            chunks, size = [], 0
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > MAX_BODY_BYTES:
                    raise FetchError(f"response larger than {MAX_BODY_BYTES} bytes")
                chunks.append(chunk)
            return resp.status_code, resp.headers, b"".join(chunks)

    def _wait_for_host(self, url: str) -> None:
        host = urlsplit(url).hostname or ""
        last = self._last_request.get(host)
        if last is not None:
            wait = self._min_interval - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = self._clock()

    def _remember_validators(self, url: str, headers: httpx.Headers) -> None:
        entry = CacheEntry(etag=headers.get("ETag"), last_modified=headers.get("Last-Modified"))
        if entry.etag or entry.last_modified:
            self.cache[url] = entry
        else:
            self.cache.pop(url, None)


def _parse_retry_after(headers: httpx.Headers) -> float | None:
    value = headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - time.time())
