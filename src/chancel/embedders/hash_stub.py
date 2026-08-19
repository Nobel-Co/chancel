"""Deterministic, offline, stdlib-only ``Embedder``.

Exists so the unit test tier runs with zero downloads and zero API keys. Not
a real embedding model: each token contributes a pseudo-random unit vector
seeded from its own hash, so texts that share vocabulary sum to similar
directions and texts that share nothing score near zero. Good enough to
prove the isolation mechanism against; not good enough for real relevance.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence

from chancel.stores.base import SparseVector

_TOKEN_RE = re.compile(r"[a-z0-9]+")
DENSE_DIM = 64


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _token_unit_vector(token: str, dim: int) -> list[float]:
    """A pseudo-random unit vector for one token, seeded from its hash so the
    same token always contributes the same direction."""
    digest = hashlib.sha256(token.encode()).digest()
    values = []
    for i in range(dim):
        # Mix the digest with the loop index so bytes don't repeat verbatim
        # once i exceeds the digest length.
        mixed = hashlib.sha256(digest + i.to_bytes(4, "big")).digest()[0]
        values.append((mixed / 255.0) * 2.0 - 1.0)
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def _token_index(token: str) -> int:
    return int(hashlib.sha256(token.encode()).hexdigest(), 16) % (2**31)


class HashStubEmbedder:
    """Deterministic offline ``Embedder``. ``dense_dim`` is fixed at 64."""

    dense_dim: int = DENSE_DIM

    def embed_dense(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            tokens = _tokenize(text)
            if not tokens:
                vectors.append(tuple(0.0 for _ in range(DENSE_DIM)))
                continue
            accum = [0.0] * DENSE_DIM
            for token in tokens:
                unit = _token_unit_vector(token, DENSE_DIM)
                for i in range(DENSE_DIM):
                    accum[i] += unit[i]
            norm = math.sqrt(sum(v * v for v in accum)) or 1.0
            vectors.append(tuple(v / norm for v in accum))
        return vectors

    def embed_sparse(self, texts: Sequence[str]) -> list[SparseVector] | None:
        result: list[SparseVector] = []
        for text in texts:
            counts: dict[int, float] = {}
            for token in _tokenize(text):
                idx = _token_index(token)
                counts[idx] = counts.get(idx, 0.0) + 1.0
            indices = tuple(sorted(counts))
            values = tuple(counts[i] for i in indices)
            result.append(SparseVector(indices=indices, values=values))
        return result
