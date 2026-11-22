"""Load and validate everything in `config/`.

Usage:  python -m pipeline.config [--config-dir config]

Checks each file against its schema (pipeline/config/schema.py), then runs
cross-file checks (references between topics, groups, filters and sources, and
the CLAUDE.md principle 7 guard). Exits 0 when valid, 1 with a list of errors
otherwise.

The private profile is validated without ever printing its values: errors show
the field path and the error message only.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from .schema import Profile, SourcesFile, TopicsFile, duplicates

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class ConfigError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class Config:
    topics: TopicsFile
    sources: SourcesFile
    profile: Profile | None  # the real private profile, only when present locally


def load_config(config_dir: Path = DEFAULT_CONFIG_DIR) -> Config:
    """Validate every config file; raise ConfigError listing every problem found."""
    errors: list[str] = []
    topics = _load(config_dir / "topics.yaml", TopicsFile, errors)
    sources = _load(config_dir / "sources.yaml", SourcesFile, errors)
    _load(config_dir / "profile.example.yaml", Profile, errors, private=True)
    profile = None
    real_profile = config_dir / "profile.yaml"
    if real_profile.exists():
        profile = _load(real_profile, Profile, errors, private=True)

    if topics is not None:
        errors += check_topics(topics)
    if topics is not None and sources is not None:
        errors += check_sources(topics, sources)

    if errors:
        raise ConfigError(errors)
    assert topics is not None and sources is not None
    return Config(topics=topics, sources=sources, profile=profile)


def check_topics(t: TopicsFile) -> list[str]:
    errors = []
    for kind, ids in (("group", [g.id for g in t.groups]), ("topic", [x.id for x in t.topics])):
        for d in duplicates(ids):
            errors.append(f"topics.yaml: duplicate {kind} id '{d}'")
    group_ids = {g.id for g in t.groups}
    for topic in t.topics:
        if topic.group not in group_ids:
            errors.append(f"topics.yaml: topic '{topic.id}': unknown group '{topic.group}'")
        for f in topic.filters_off:
            if f not in t.global_filters:
                errors.append(
                    f"topics.yaml: topic '{topic.id}': filters_off names unknown filter '{f}'"
                )
    return errors


def check_sources(t: TopicsFile, s: SourcesFile) -> list[str]:
    errors = [
        f"sources.yaml: duplicate source id '{d}'" for d in duplicates([x.id for x in s.sources])
    ]
    topics = {x.id: x for x in t.topics}
    for src in s.sources:
        for tid in src.topics:
            topic = topics.get(tid)
            if topic is None:
                errors.append(f"sources.yaml: source '{src.id}': unknown topic '{tid}'")
            # CLAUDE.md principle 7. Remove this check when the Phase 3 spoiler filter ships.
            elif topic.spoiler_policy == "fail_closed" and src.status != "disabled":
                errors.append(
                    f"sources.yaml: source '{src.id}' feeds spoiler-protected topic '{tid}' and "
                    "must stay `status: disabled` until the spoiler filter exists "
                    "(CLAUDE.md principle 7; DESIGN.md §14 phase 3)"
                )
    return errors


def _load[M: BaseModel](
    path: Path, model: type[M], errors: list[str], *, private: bool = False
) -> M | None:
    name = path.name
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{name}: file not found")
        return None
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        # The full YAML error quotes the offending line; never echo private content.
        detail = "" if private else f": {e}"
        errors.append(f"{name}: invalid YAML{where}{detail}")
        return None
    if data is None:
        data = {}
    try:
        return model.model_validate(data)
    except ValidationError as e:
        errors.extend(
            f"{name}: {_format_loc(err['loc'], data)}: {err['msg']}" for err in e.errors()
        )
        return None


def _format_loc(loc: tuple[Any, ...], data: Any) -> str:
    """Render a pydantic error location, naming list items by their `id` when they have one."""
    parts: list[str] = []
    node = data
    for key in loc:
        if isinstance(key, int) and isinstance(node, list) and 0 <= key < len(node):
            item = node[key]
            item_id = item.get("id") if isinstance(item, dict) else None
            parts.append(f"[{key}]" + (f"({item_id})" if isinstance(item_id, str) else ""))
            node = item
        elif isinstance(key, str) and isinstance(node, dict) and key in node:
            parts.append(f".{key}")
            node = node[key]
        else:
            # Model-validator names (e.g. "function-after[...]") or missing keys.
            if isinstance(key, str) and not key.startswith("function-"):
                parts.append(f".{key}")
            node = None
    return "".join(parts).lstrip(".") or "(root)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.config", description="Validate Skein config files."
    )
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config_dir)
    except ConfigError as e:
        print(f"Config invalid ({len(e.errors)} error(s)):", file=sys.stderr)
        for err in e.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    profile_note = " + local profile.yaml" if cfg.profile is not None else ""
    print(
        f"Config OK: {len(cfg.topics.topics)} topics, {len(cfg.sources.sources)} sources"
        f"{profile_note}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
