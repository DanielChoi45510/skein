"""Sample feed for frontend development: python -m pipeline.sample --out DIR

Runs the whole pipeline offline over the test fixtures (tests/fixtures/config and
tests/fixtures/http) with the hashing embedder, at the fixtures' fixed time, into
a throwaway state dir. No network, no model. Dev-only: needs a repo checkout.

Hashing-embedder scores are meaningless, so the relevance threshold is set to 0
(on a temp copy of the config) to make every fixture item show up.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import tempfile
from pathlib import Path

import httpx
import yaml

from .process.embed import HashingEmbedder
from .run import run

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
FIXTURE_NOW = dt.datetime(2026, 11, 21, 12, 0, tzinfo=dt.UTC)


def fixture_transport() -> httpx.MockTransport:
    http_dir = FIXTURES / "http"
    routes = json.loads((http_dir / "routes.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        name = routes.get(str(request.url))
        if name is None:
            return httpx.Response(404)
        return httpx.Response(200, content=(http_dir / name).read_bytes())

    return httpx.MockTransport(handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.sample")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not FIXTURES.is_dir():
        print("tests/fixtures not found: run from a repo checkout", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        state, config = Path(tmp) / "state", Path(tmp) / "config"
        shutil.copytree(FIXTURES / "config", config)
        topics = yaml.safe_load((config / "topics.yaml").read_text())
        topics["defaults"]["relevance_threshold"] = 0.0
        (config / "topics.yaml").write_text(yaml.safe_dump(topics, sort_keys=False))
        run(
            state,
            out_dir=args.out,
            config_dir=config,
            now=FIXTURE_NOW,
            transport=fixture_transport(),
            sleep=lambda _: None,
            embedder=HashingEmbedder(),
        )
    print(f"Sample feed written to {args.out / 'feed'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
