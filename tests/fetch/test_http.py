"""Shared HTTP client: UA, conditional GET, retries, rate limiting, size cap."""

from __future__ import annotations

import httpx
import pytest

from pipeline.fetch.http import (
    MAX_RETRY_AFTER,
    MIN_INTERVAL_PER_HOST,
    FetchError,
    HttpFetcher,
    user_agent,
)
from pipeline.models import CacheEntry

from ..conftest import FakeClock, FakeWeb

URL = "https://feeds.example.com/world.xml"


def fetcher(web: FakeWeb, clock: FakeClock, cache: dict | None = None) -> HttpFetcher:
    return HttpFetcher(
        {} if cache is None else cache, transport=web.transport, sleep=clock.sleep, clock=clock
    )


def sequence(*responses: httpx.Response | Exception):
    """Handler returning the given responses (or raising the given errors) in order."""
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return handler


# ───────────────────────────── User-Agent ─────────────────────────────


def test_user_agent_generic_without_repo() -> None:
    assert user_agent({}) == "Skein/0.1 (self-hosted personal feed reader)"


def test_user_agent_includes_repo_in_actions() -> None:
    ua = user_agent({"GITHUB_REPOSITORY": "someone/skein"})
    assert ua == "Skein/0.1 (personal feed reader; +https://github.com/someone/skein)"


@pytest.mark.parametrize("repo", ["", "not a repo", "a/b/c", "x/y\r\nInjected: 1", "x/y\n"])
def test_user_agent_ignores_malformed_repo(repo: str) -> None:
    assert user_agent({"GITHUB_REPOSITORY": repo}) == user_agent({})


def test_requests_send_user_agent(clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/skein")
    web = FakeWeb({URL: lambda r: httpx.Response(200, content=b"x")})
    fetcher(web, clock).get(URL)
    assert web.requests[0].headers["User-Agent"].endswith("+https://github.com/someone/skein)")


def test_timeouts_are_configured(clock: FakeClock) -> None:
    timeout = fetcher(FakeWeb(), clock).client.timeout
    assert timeout.connect == 10.0
    assert timeout.read == 20.0


# ───────────────────────────── conditional GET ─────────────────────────────


def test_200_stores_validators(clock: FakeClock) -> None:
    headers = {"ETag": '"v1"', "Last-Modified": "Sat, 21 Nov 2026 10:00:00 GMT"}
    web = FakeWeb({URL: lambda r: httpx.Response(200, content=b"feed", headers=headers)})
    cache: dict[str, CacheEntry] = {}
    result = fetcher(web, clock, cache).get(URL)
    assert (result.status, result.content) == ("ok", b"feed")
    assert cache[URL] == CacheEntry(etag='"v1"', last_modified="Sat, 21 Nov 2026 10:00:00 GMT")


def test_conditional_headers_sent_and_304_is_unchanged(clock: FakeClock) -> None:
    web = FakeWeb({URL: lambda r: httpx.Response(304)})
    cache = {URL: CacheEntry(etag='"v1"', last_modified="Sat, 21 Nov 2026 10:00:00 GMT")}
    result = fetcher(web, clock, cache).get(URL)
    assert result.status == "unchanged"
    sent = web.requests[0].headers
    assert sent["If-None-Match"] == '"v1"'
    assert sent["If-Modified-Since"] == "Sat, 21 Nov 2026 10:00:00 GMT"


def test_response_without_validators_clears_cache_entry(clock: FakeClock) -> None:
    web = FakeWeb({URL: lambda r: httpx.Response(200, content=b"feed")})
    cache = {URL: CacheEntry(etag='"old"')}
    fetcher(web, clock, cache).get(URL)
    assert URL not in cache


def test_no_conditional_headers_without_cache(clock: FakeClock) -> None:
    web = FakeWeb({URL: lambda r: httpx.Response(200, content=b"feed")})
    fetcher(web, clock).get(URL)
    assert "If-None-Match" not in web.requests[0].headers
    assert "If-Modified-Since" not in web.requests[0].headers


# ───────────────────────────── retries ─────────────────────────────


def test_retries_5xx_with_backoff_then_succeeds(clock: FakeClock) -> None:
    web = FakeWeb(
        {
            URL: sequence(
                httpx.Response(503), httpx.Response(502), httpx.Response(200, content=b"ok")
            )
        }
    )
    f = fetcher(web, clock)
    assert f.get(URL).content == b"ok"
    assert len(web.requests) == 3
    # backoff 2 s then 4 s; the rate-limit wait is already covered by the backoff
    assert clock.sleeps == [2.0, 4.0]


def test_429_honors_retry_after(clock: FakeClock) -> None:
    web = FakeWeb(
        {
            URL: sequence(
                httpx.Response(429, headers={"Retry-After": "5"}),
                httpx.Response(200, content=b"ok"),
            )
        }
    )
    assert fetcher(web, clock).get(URL).status == "ok"
    assert clock.sleeps == [5.0]


def test_retry_after_is_capped(clock: FakeClock) -> None:
    web = FakeWeb(
        {
            URL: sequence(
                httpx.Response(429, headers={"Retry-After": "3600"}),
                httpx.Response(200, content=b"ok"),
            )
        }
    )
    fetcher(web, clock).get(URL)
    assert clock.sleeps == [MAX_RETRY_AFTER]


def test_gives_up_after_retries(clock: FakeClock) -> None:
    web = FakeWeb({URL: lambda r: httpx.Response(503)})
    with pytest.raises(FetchError, match="HTTP 503 after 3 attempts"):
        fetcher(web, clock).get(URL)
    assert len(web.requests) == 3


def test_timeout_is_retried_then_reported(clock: FakeClock) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    web = FakeWeb({URL: timeout})
    with pytest.raises(FetchError, match=r"timeout \(ReadTimeout\) after 3 attempts"):
        fetcher(web, clock).get(URL)


def test_network_error_recovers(clock: FakeClock) -> None:
    web = FakeWeb(
        {URL: sequence(httpx.ConnectError("refused"), httpx.Response(200, content=b"ok"))}
    )
    assert fetcher(web, clock).get(URL).status == "ok"


@pytest.mark.parametrize("status", [400, 403, 404, 410])
def test_client_errors_are_not_retried(clock: FakeClock, status: int) -> None:
    web = FakeWeb({URL: lambda r: httpx.Response(status)})
    with pytest.raises(FetchError, match=f"HTTP {status}"):
        fetcher(web, clock).get(URL)
    assert len(web.requests) == 1


def test_oversized_response_is_rejected(clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pipeline.fetch.http.MAX_BODY_BYTES", 10)
    web = FakeWeb({URL: lambda r: httpx.Response(200, content=b"x" * 11)})
    with pytest.raises(FetchError, match="larger than 10 bytes"):
        fetcher(web, clock).get(URL)


# ───────────────────────────── rate limiting ─────────────────────────────


def test_same_host_requests_are_spaced(clock: FakeClock) -> None:
    other = "https://feeds.example.com/other.xml"
    ok = lambda r: httpx.Response(200, content=b"ok")  # noqa: E731
    web = FakeWeb({URL: ok, other: ok})
    f = fetcher(web, clock)
    f.get(URL)
    clock.now += 0.5
    f.get(other)
    assert clock.sleeps == [pytest.approx(MIN_INTERVAL_PER_HOST - 0.5)]


def test_different_hosts_are_not_delayed(clock: FakeClock) -> None:
    other = "https://atom.example.org/gadgets.atom"
    ok = lambda r: httpx.Response(200, content=b"ok")  # noqa: E731
    web = FakeWeb({URL: ok, other: ok})
    f = fetcher(web, clock)
    f.get(URL)
    f.get(other)
    assert clock.sleeps == []
