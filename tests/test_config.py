"""Config schema + validator tests.

Negative cases mutate a copy of the fixture config in tests/fixtures/config/, so
they don't depend on the ids in the real config/ files (which the owner edits).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from pipeline.config import ConfigError, load_config
from pipeline.config.validate import main

from .conftest import FIXTURE_CONFIG, REPO_CONFIG

CONFIG_FILES = ("topics.yaml", "sources.yaml", "profile.example.yaml")


def copy_config(src: Path, dest: Path) -> Path:
    """Copy the committed files only (never a local private profile.yaml)."""
    for name in CONFIG_FILES:
        shutil.copy(src / name, dest / name)
    return dest


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    return copy_config(FIXTURE_CONFIG, tmp_path)


def edit(config_dir: Path, name: str, fn: Callable[[Any], None]) -> None:
    path = config_dir / name
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def topic(data: dict, topic_id: str) -> dict:
    return next(t for t in data["topics"] if t["id"] == topic_id)


def source(data: dict, source_id: str) -> dict:
    return next(s for s in data["sources"] if s["id"] == source_id)


def errors_for(config_dir: Path) -> str:
    with pytest.raises(ConfigError) as exc:
        load_config(config_dir)
    return "\n".join(exc.value.errors)


# ───────────────────────────── valid config ─────────────────────────────


def test_committed_config_is_valid(tmp_path: Path) -> None:
    cfg = load_config(copy_config(REPO_CONFIG, tmp_path))
    assert len(cfg.topics.topics) > 0
    assert len(cfg.sources.sources) > 0
    assert cfg.profile is None


def test_fixture_config_is_valid(config_dir: Path) -> None:
    cfg = load_config(config_dir)
    assert len(cfg.topics.topics) > 0
    assert len(cfg.sources.sources) > 0
    assert cfg.profile is None


def test_cli_exit_codes(config_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--config-dir", str(config_dir)]) == 0
    edit(config_dir, "topics.yaml", lambda d: topic(d, "world").update(group="nope"))
    assert main(["--config-dir", str(config_dir)]) == 1
    assert "unknown group 'nope'" in capsys.readouterr().err


def test_local_profile_is_validated_when_present(config_dir: Path) -> None:
    shutil.copy(config_dir / "profile.example.yaml", config_dir / "profile.yaml")
    assert load_config(config_dir).profile is not None


# ───────────────────────────── topics.yaml ─────────────────────────────


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        pytest.param(
            lambda d: topic(d, "world").update(descripton="typo"),
            "descripton: Extra inputs are not permitted",
            id="unknown-key",
        ),
        pytest.param(
            lambda d: topic(d, "world").update(group="sports"),
            "topic 'world': unknown group 'sports'",
            id="unknown-group",
        ),
        pytest.param(
            lambda d: d["topics"].append(dict(topic(d, "world"))),
            "duplicate topic id 'world'",
            id="duplicate-topic",
        ),
        pytest.param(
            lambda d: topic(d, "gadgets").update(filters_off=["sarcasm"]),
            "filters_off names unknown filter 'sarcasm'",
            id="unknown-filter",
        ),
        pytest.param(
            lambda d: topic(d, "gadgets").pop("max_per_week"),
            "mode 'flat' requires a cap",
            id="flat-without-cap",
        ),
        pytest.param(
            lambda d: topic(d, "trackers").pop("threads"),
            "mode 'tracker' requires a non-empty `threads`",
            id="tracker-without-threads",
        ),
        pytest.param(
            lambda d: topic(d, "gadgets").update(threads=[{"id": "x", "title": "X"}]),
            "`threads` is only allowed for modes 'tracker' and 'fixed'",
            id="threads-on-flat",
        ),
        pytest.param(
            lambda d: topic(d, "markets")["threads"].append({"id": "energy", "title": "Again"}),
            "duplicate thread ids: energy",
            id="duplicate-thread",
        ),
        pytest.param(
            lambda d: topic(d, "world").update(mode="infinite"),
            "mode: Input should be",
            id="unknown-mode",
        ),
        pytest.param(
            lambda d: topic(d, "world").update(id="AI News"),
            "String should match pattern",
            id="bad-id",
        ),
    ],
)
def test_invalid_topics(config_dir: Path, mutate: Callable, expected: str) -> None:
    edit(config_dir, "topics.yaml", mutate)
    assert expected in errors_for(config_dir)


# ───────────────────────────── sources.yaml ─────────────────────────────


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        pytest.param(
            lambda d: source(d, "example-world").update(topics=["sports"]),
            "source 'example-world': unknown topic 'sports'",
            id="unknown-topic",
        ),
        pytest.param(
            lambda d: source(d, "example-world").update(weight=2.0),
            "less than or equal to 1.5",
            id="weight-out-of-range",
        ),
        pytest.param(
            lambda d: source(d, "example-world").pop("url"),
            "rss sources require `url`",
            id="rss-without-url",
        ),
        pytest.param(
            lambda d: source(d, "example-reddit").update(url="https://reddit.com/r/x"),
            "reddit sources must not set `url`",
            id="reddit-with-url",
        ),
        pytest.param(
            lambda d: source(d, "example-world").update(lean="far-left"),
            "lean: Input should be",
            id="bad-lean",
        ),
        pytest.param(
            lambda d: d["sources"].append(dict(source(d, "example-world"))),
            "duplicate source id 'example-world'",
            id="duplicate-source",
        ),
    ],
)
def test_invalid_sources(config_dir: Path, mutate: Callable, expected: str) -> None:
    edit(config_dir, "sources.yaml", mutate)
    assert expected in errors_for(config_dir)


@pytest.mark.parametrize(
    ("relevance", "expected"),
    [
        pytest.param({"threshold": 0.2, "skip": True}, "exactly one of", id="both"),
        pytest.param({}, "exactly one of", id="neither"),
        pytest.param({"threshold": 1.5}, "less than or equal to 1", id="out-of-range"),
    ],
)
def test_invalid_source_relevance(config_dir: Path, relevance: dict, expected: str) -> None:
    edit(
        config_dir, "sources.yaml", lambda d: source(d, "example-world").update(relevance=relevance)
    )
    assert expected in errors_for(config_dir)


def test_relevance_skip_needs_single_topic(config_dir: Path) -> None:
    edit(
        config_dir,
        "sources.yaml",
        lambda d: source(d, "example-hn").update(relevance={"skip": True}),
    )
    assert "needs exactly one topic" in errors_for(config_dir)


def test_valid_relevance_overrides(config_dir: Path) -> None:
    edit(
        config_dir,
        "sources.yaml",
        lambda d: source(d, "example-world").update(relevance={"skip": True}),
    )
    edit(
        config_dir,
        "sources.yaml",
        lambda d: source(d, "example-hn").update(relevance={"threshold": 0.1}),
    )
    edit(config_dir, "topics.yaml", lambda d: topic(d, "world").update(relevance_threshold=0.45))
    load_config(config_dir)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: d["defaults"].pop("relevance_threshold"), id="default-missing"),
        pytest.param(
            lambda d: d["defaults"].update(relevance_threshold=-0.1), id="default-negative"
        ),
        pytest.param(lambda d: topic(d, "world").update(relevance_threshold=2), id="topic-over-1"),
    ],
)
def test_invalid_relevance_threshold(config_dir: Path, mutate: Callable) -> None:
    edit(config_dir, "topics.yaml", mutate)
    assert "relevance_threshold" in errors_for(config_dir)


@pytest.mark.parametrize("status", ["trial", "active"])
def test_spoiler_protected_source_must_stay_disabled(config_dir: Path, status: str) -> None:
    """CLAUDE.md principle 7: the Genshin source stays disabled until the spoiler filter exists."""
    edit(
        config_dir,
        "sources.yaml",
        lambda d: source(d, "example-leaks").update(status=status),
    )
    assert "must stay `status: disabled`" in errors_for(config_dir)


# ───────────────────────────── profile (private) ─────────────────────────────

SECRET = "SENTINEL-private-value-9f3a"


def test_profile_errors_never_echo_values(config_dir: Path) -> None:
    profile = yaml.safe_load((config_dir / "profile.example.yaml").read_text())
    profile["jobs"]["seeking"] = [SECRET]
    profile["jobs"]["constraints"]["clearance_ok"] = SECRET
    profile["health"]["goals"] = {"nested": SECRET}
    (config_dir / "profile.yaml").write_text(yaml.safe_dump(profile))

    out = errors_for(config_dir)
    assert "profile.yaml: jobs.seeking[0]" in out
    assert "profile.yaml: jobs.constraints.clearance_ok" in out
    assert SECRET not in out


def test_profile_yaml_syntax_error_never_echoes_line(config_dir: Path) -> None:
    (config_dir / "profile.yaml").write_text(f"jobs:\n  skills_summary: [{SECRET}\n")
    out = errors_for(config_dir)
    assert "profile.yaml: invalid YAML at line" in out
    assert SECRET not in out
