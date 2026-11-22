"""The pipeline's state directory (the `data` branch in CI; DESIGN §10.1).

All writes happen once, at the end of a run (`State.save`), so a run that crashes
midway leaves the previous state untouched. In particular the HTTP cache is never
saved without the items it corresponds to; otherwise the next run would get a
304 for entries it never stored.

Items live in `items/YYYY-MM-DD.ndjson`, partitioned by `first_seen_at` (UTC),
one JSON object per line with sorted keys, rows sorted by id. Rewriting an
unchanged partition produces identical bytes, so reruns leave no diff. Only the
last ITEM_WINDOW_DAYS days of partitions are loaded; older ones are left alone.
(Lookback windows are ≤ 30 days, so an entry old enough to fall outside the
loaded window is dropped by normalization before it could be re-added.)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from .models import CacheEntry, Item, SourceHealth

HTTP_CACHE = "http_cache.json"
SOURCE_HEALTH = "source_health.json"
ITEMS_DIR = "items"
ITEM_WINDOW_DAYS = 30

_cache_adapter = TypeAdapter(dict[str, CacheEntry])
_health_adapter = TypeAdapter(dict[str, SourceHealth])


class State:
    def __init__(self, root: Path, now: dt.datetime):
        self.root = root
        self.items: dict[str, Item] = load_items(root / ITEMS_DIR, now.date())
        self.http_cache: dict[str, CacheEntry] = _cache_adapter.validate_python(
            read_json(root / HTTP_CACHE, {})
        )
        self.health: dict[str, SourceHealth] = _health_adapter.validate_python(
            read_json(root / SOURCE_HEALTH, {})
        )

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        save_items(self.root / ITEMS_DIR, self.items.values())
        write_json(self.root / SOURCE_HEALTH, _health_adapter.dump_python(self.health, mode="json"))
        # Last: validators are only useful once the items they cover are on disk.
        write_json(self.root / HTTP_CACHE, _cache_adapter.dump_python(self.http_cache, mode="json"))


def partition_name(day: dt.date) -> str:
    return f"{day.isoformat()}.ndjson"


def load_items(items_dir: Path, today: dt.date) -> dict[str, Item]:
    oldest = today - dt.timedelta(days=ITEM_WINDOW_DAYS)
    items: dict[str, Item] = {}
    for path in sorted(items_dir.glob("*.ndjson")):
        try:
            day = dt.date.fromisoformat(path.stem)
        except ValueError:
            continue
        if day < oldest:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = Item.model_validate_json(line)
                items[item.id] = item
    return items


def save_items(items_dir: Path, items: Iterable[Item]) -> None:
    by_day: dict[dt.date, list[Item]] = {}
    for item in items:
        by_day.setdefault(item.first_seen_at.astimezone(dt.UTC).date(), []).append(item)
    for day, rows in by_day.items():
        lines = [
            json.dumps(i.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
            for i in sorted(rows, key=lambda i: i.id)
        ]
        write_text_atomic(items_dir / partition_name(day), "\n".join(lines) + "\n")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data: Any) -> None:
    """Write deterministic JSON atomically (sorted keys, so reruns produce identical bytes)."""
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    write_text_atomic(path, text)


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
