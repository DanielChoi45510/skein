"""The real embedding model. Skipped unless it's installed and already in the local cache.

CI never installs the `[embed]` extra, so this runs only on a developer machine.
The autouse fixture in conftest.py sets HF_HUB_OFFLINE, so it can't download.
"""

from __future__ import annotations

import pytest

from pipeline.process.embed import MODEL_NAME

pytestmark = pytest.mark.model


def _model_cached() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return False
    return isinstance(try_to_load_from_cache(MODEL_NAME, "config.json"), str)


@pytest.fixture(scope="module")
def embedder():
    if not _model_cached():
        pytest.skip(f"{MODEL_NAME} not installed/cached")
    from pipeline.process.embed import SentenceTransformerEmbedder

    return SentenceTransformerEmbedder()


def test_vectors_are_normalized(embedder) -> None:
    import numpy as np

    v = embedder.embed(["one", "two"], "passage")
    assert v.shape == (2, 384)
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-5)


@pytest.mark.parametrize("instruction", [False, True])
def test_semantic_sanity(embedder, instruction: bool) -> None:
    embedder.query_instruction = instruction
    [anchor] = embedder.embed(["Major world events: elections and diplomacy"], "query")
    on, off = embedder.embed(
        ["Coalition talks resume after a close parliamentary election", "We tested 12 desk lamps"],
        "passage",
    )
    assert float(anchor @ on) > float(anchor @ off) + 0.1
