"""State dir: threads and centroids (DESIGN §10.1)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pytest

from pipeline.models import Thread
from pipeline.state import CENTROID_IDS, CENTROIDS, THREADS, State, write_json

NOW = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.UTC)


def thread(thread_id: str, **kw) -> Thread:
    base = {
        "id": thread_id,
        "topic_id": "world",
        "kind": "story",
        "title": "Elections · Germany",
        "state": "active",
        "created_at": NOW - dt.timedelta(days=2),
        "last_item_at": NOW - dt.timedelta(hours=3),
        "item_ids": ["b", "a"],
    }
    return Thread.model_validate(base | kw)


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(root.iterdir()) if p.is_file()}


def test_empty_state_has_no_threads(tmp_path: Path) -> None:
    state = State(tmp_path, NOW)
    assert state.threads == {}
    assert state.centroids == {}
    state.save()
    reloaded = State(tmp_path, NOW)
    assert reloaded.threads == {} and reloaded.centroids == {}


def test_threads_and_centroids_round_trip(tmp_path: Path) -> None:
    state = State(tmp_path, NOW)
    state.threads = {"t2": thread("t2"), "t1": thread("t1", state="pending", item_ids=["c"])}
    state.centroids = {
        "t2": np.array([0.6, 0.8, 0.0], np.float32),
        "t1": np.array([1.0, 0.0, 0.0], np.float32),
    }
    state.save()

    reloaded = State(tmp_path, NOW)
    assert reloaded.threads == state.threads
    assert sorted(reloaded.centroids) == ["t1", "t2"]
    for tid, vec in state.centroids.items():
        assert reloaded.centroids[tid].dtype == np.float32
        np.testing.assert_array_equal(reloaded.centroids[tid], vec)
    # Item order inside a thread is attach order, not sorted.
    assert reloaded.threads["t2"].item_ids == ["b", "a"]


def test_threads_file_is_sorted_by_id(tmp_path: Path) -> None:
    state = State(tmp_path, NOW)
    state.threads = {"zz": thread("zz"), "aa": thread("aa")}
    state.save()
    text = (tmp_path / THREADS).read_text()
    assert text.index('"id": "aa"') < text.index('"id": "zz"')


def test_resave_is_byte_identical(tmp_path: Path) -> None:
    state = State(tmp_path, NOW)
    state.threads = {"t1": thread("t1")}
    state.centroids = {"t1": np.array([0.6, 0.8], np.float32)}
    state.save()
    first = snapshot(tmp_path)
    assert {THREADS, CENTROIDS, CENTROID_IDS} <= set(first)

    State(tmp_path, NOW).save()
    assert snapshot(tmp_path) == first


def test_centroid_rows_must_match_ids(tmp_path: Path) -> None:
    state = State(tmp_path, NOW)
    state.centroids = {"t1": np.array([1.0, 0.0], np.float32)}
    state.save()
    write_json(tmp_path / CENTROID_IDS, ["t1", "t2"])
    with pytest.raises(ValueError, match="expected 2 rows"):
        State(tmp_path, NOW)
