"""CLI: python -m pipeline run --state DIR [--config-dir DIR]"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import ConfigError
from .config.validate import DEFAULT_CONFIG_DIR
from .process.embed import HashingEmbedder
from .run import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="run the pipeline once")
    p_run.add_argument("--state", type=Path, required=True, help="state directory")
    p_run.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    p_run.add_argument(
        "--embedder",
        choices=["model", "hashing"],
        default="model",
        help="'hashing' is a dependency-free stand-in for development; scores are not meaningful",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # we log one line per source instead
    try:
        embedder = HashingEmbedder() if args.embedder == "hashing" else None
        report = run(args.state, config_dir=args.config_dir, embedder=embedder)
    except ConfigError as e:
        print("Config invalid:", file=sys.stderr)
        for err in e.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    ok = len(report.outcomes)
    print(
        f"Fetched {ok} source(s), {len(report.errors)} error(s), {len(report.entries)} entries, "
        f"{len(report.new_item_ids)} new item(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
