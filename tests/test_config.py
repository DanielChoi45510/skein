"""Config schema + validator tests. Each negative case mutates a copy of the real config."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from pipeline.config import ConfigError, load_config
from pipeline.config.validate import main

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config"
CONFIG_FILES = ("topics.yaml", "sources.yaml", "profile.example.yaml")


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """A copy of the committed config files (never the local private profile)."""
    for name in CONFIG_FILES:
        shutil.copy(REPO_CONFIG / name, tmp_path / name)
    return tmp_path


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


def test_committed_config_is_valid(config_dir: Path) -> None:
    cfg = load_config(config_dir)
    assert len(cfg.topics.topics) > 0
    assert len(cfg.sources.sources) > 0
    assert cfg.profile is None


def test_cli_exit_codes(config_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--config-dir", str(config_dir)]) == 0
    edit(config_dir, "topics.yaml", lambda d: topic(d, "ai-news").update(group="nope"))
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
            lambda d: topic(d, "ai-news").update(descripton="typo"),
            "descripton: Extra inputs are not permitted",
            id="unknown-key",
        ),
        pytest.param(
            lambda d: topic(d, "ai-news").update(group="sports"),
            "topic 'ai-news': unknown group 'sports'",
            id="unknown-group",
        ),
        pytest.param(
            lambda d: d["topics"].append(dict(topic(d, "ai-news"))),
            "duplicate topic id 'ai-news'",
            id="duplicate-topic",
        ),
        pytest.param(
            lambda d: topic(d, "everyday-upgrades").update(filters_off=["sarcasm"]),
            "filters_off names unknown filter 'sarcasm'",
            id="unknown-filter",
        ),
        pytest.param(
            lambda d: topic(d, "ai-practice").pop("max_per_day"),
            "mode 'flat' requires a cap",
            id="flat-without-cap",
        ),
        pytest.param(
            lambda d: topic(d, "tech-trackers").pop("threads"),
            "mode 'tracker' requires a non-empty `threads`",
            id="tracker-without-threads",
        ),
        pytest.param(
            lambda d: topic(d, "ai-practice").update(threads=[{"id": "x", "title": "X"}]),
            "`threads` is only allowed for modes 'tracker' and 'fixed'",
            id="threads-on-flat",
        ),
        pytest.param(
            lambda d: topic(d, "markets")["threads"].append({"id": "energy", "title": "Again"}),
            "duplicate thread ids: energy",
            id="duplicate-thread",
        ),
        pytest.param(
            lambda d: topic(d, "ai-news").update(mode="infinite"),
            "mode: Input should be",
            id="unknown-mode",
        ),
        pytest.param(
            lambda d: topic(d, "ai-news").update(id="AI News"),
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
            lambda d: source(d, "nyt-world").update(topics=["sports"]),
            "source 'nyt-world': unknown topic 'sports'",
            id="unknown-topic",
        ),
        pytest.param(
            lambda d: source(d, "nyt-world").update(weight=2.0),
            "less than or equal to 1.5",
            id="weight-out-of-range",
        ),
        pytest.param(
            lambda d: source(d, "nyt-world").pop("url"),
            "rss sources require `url`",
            id="rss-without-url",
        ),
        pytest.param(
            lambda d: source(d, "reddit-genshin-leaks").update(url="https://reddit.com/r/x"),
            "reddit sources must not set `url`",
            id="reddit-with-url",
        ),
        pytest.param(
            lambda d: source(d, "nyt-world").update(lean="far-left"),
            "lean: Input should be",
            id="bad-lean",
        ),
        pytest.param(
            lambda d: d["sources"].append(dict(source(d, "nyt-world"))),
            "duplicate source id 'nyt-world'",
            id="duplicate-source",
        ),
    ],
)
def test_invalid_sources(config_dir: Path, mutate: Callable, expected: str) -> None:
    edit(config_dir, "sources.yaml", mutate)
    assert expected in errors_for(config_dir)


@pytest.mark.parametrize("status", ["trial", "active"])
def test_spoiler_protected_source_must_stay_disabled(config_dir: Path, status: str) -> None:
    """CLAUDE.md principle 7: the Genshin source stays disabled until the spoiler filter exists."""
    edit(
        config_dir,
        "sources.yaml",
        lambda d: source(d, "reddit-genshin-leaks").update(status=status),
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
