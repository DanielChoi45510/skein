"""Text embeddings (DESIGN §6.4).

Two implementations of one small protocol:
- SentenceTransformerEmbedder: the real model, small and CPU-friendly. Needs the
  optional `[embed]` extra; imported lazily so nothing else depends on torch.
- HashingEmbedder: deterministic bag-of-words hashing. No dependencies, no
  downloads. Used by tests and for offline development; its scores mean little.

Vectors are L2-normalized float32, so a dot product is the cosine similarity.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Literal, Protocol

import numpy as np

MODEL_NAME = "BAAI/bge-small-en-v1.5"

# bge models are trained with this prefix on the *query* side of retrieval. Topic
# anchors play the query role, items the passage role. Whether it helps here is
# decided by calibration (python -m pipeline.calibrate).
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
USE_QUERY_INSTRUCTION = False

Kind = Literal["query", "passage"]


class Embedder(Protocol):
    def embed(self, texts: Sequence[str], kind: Kind) -> np.ndarray:
        """Return an (n, d) array of L2-normalized vectors."""
        ...


class SentenceTransformerEmbedder:
    def __init__(
        self, model_name: str = MODEL_NAME, *, query_instruction: bool = USE_QUERY_INSTRUCTION
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # pragma: no cover - depends on the environment
            raise RuntimeError(
                'The embedding model needs the optional extra: pip install -e ".[embed]"'
            ) from e
        self._model = SentenceTransformer(model_name, device="cpu")
        self.query_instruction = query_instruction

    def embed(self, texts: Sequence[str], kind: Kind) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._model.get_sentence_embedding_dimension() or 0), np.float32)
        prefix = BGE_QUERY_INSTRUCTION if kind == "query" and self.query_instruction else ""
        vectors = self._model.encode(
            [prefix + t for t in texts],
            batch_size=64,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


class HashingEmbedder:
    """Deterministic bag-of-words vectors (lowercased word tokens hashed into `dim` buckets)."""

    _TOKEN = re.compile(r"[a-z0-9]+")

    def __init__(self, dim: int = 512):
        self.dim = dim

    def embed(self, texts: Sequence[str], kind: Kind) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), np.float32)
        for row, text in enumerate(texts):
            for token in self._TOKEN.findall(text.lower()):
                digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
                out[row, int.from_bytes(digest, "little") % self.dim] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms
