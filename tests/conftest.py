"""Shared test helpers. Nothing here touches the network."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO_CONFIG = ROOT / "config"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE_CONFIG = FIXTURES / "config"
HTTP_FIXTURES = FIXTURES / "http"

# URL → fixture file, for the sources in tests/fixtures/config/sources.yaml.
FIXTURE_ROUTES = {
    "https://feeds.example.com/world.xml": "world.rss.xml",
    "https://atom.example.org/gadgets.atom": "gadgets.atom",
    "https://hn.example.net/frontpage?points=200": "hn.rss.xml",
    "https://www.reddit.com/r/ExampleNews/hot.json?limit=100&raw_json=1": "reddit_hot.json",
}


def http_fixture(name: str) -> bytes:
    return (HTTP_FIXTURES / name).read_bytes()


Handler = Callable[[httpx.Request], httpx.Response]


class FakeWeb:
    """An httpx MockTransport with per-URL handlers and a log of every request."""

    def __init__(self, routes: dict[str, Handler] | None = None):
        self.routes: dict[str, Handler] = dict(routes or {})
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def serve_fixtures(self, **headers: str) -> FakeWeb:
        """Serve every FIXTURE_ROUTES file, honoring If-None-Match against an `etag` header."""
        for url, name in FIXTURE_ROUTES.items():
            self.routes[url] = _static(http_fixture(name), headers)
        return self

    def urls(self) -> list[str]:
        return [str(r.url) for r in self.requests]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self.routes.get(str(request.url))
        if handler is None:
            raise AssertionError(f"unexpected request: {request.url}")
        return handler(request)


def _static(body: bytes, headers: dict[str, str]) -> Handler:
    resp_headers = {k.replace("_", "-"): v for k, v in headers.items()}

    def handler(request: httpx.Request) -> httpx.Response:
        etag = resp_headers.get("etag")
        if etag and request.headers.get("If-None-Match") == etag:
            return httpx.Response(304, headers=resp_headers)
        return httpx.Response(200, content=body, headers=resp_headers)

    return handler


class FakeClock:
    """Monotonic clock + sleep that advance together, recording every sleep."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # CI sets GITHUB_REPOSITORY; tests that need it set it explicitly.
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    # Tests never touch the network: the model may only load from the local cache.
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()
