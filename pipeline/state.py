"""The pipeline's state directory (the `data` branch in CI; DESIGN §10.1).

All writes happen once, at the end of a run (`State.save`), so a run that crashes
midway leaves the previous state untouched. In particular the HTTP cache is never
saved without the items it corresponds to; otherwise the next run would get a
304 for entries it never stored.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from .models import CacheEntry, SourceHealth

HTTP_CACHE = "http_cache.json"
SOURCE_HEALTH = "source_health.json"

_cache_adapter = TypeAdapter(dict[str, CacheEntry])
_health_adapter = TypeAdapter(dict[str, SourceHealth])


class State:
    def __init__(self, root: Path):
        self.root = root
        self.http_cache: dict[str, CacheEntry] = _cache_adapter.validate_python(
            read_json(root / HTTP_CACHE, {})
        )
        self.health: dict[str, SourceHealth] = _health_adapter.validate_python(
            read_json(root / SOURCE_HEALTH, {})
        )

    def save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        write_json(self.root / HTTP_CACHE, _cache_adapter.dump_python(self.http_cache, mode="json"))
        write_json(self.root / SOURCE_HEALTH, _health_adapter.dump_python(self.health, mode="json"))


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
