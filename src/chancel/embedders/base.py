"""``Embedder`` protocol: text in, vectors out.

Dense embedding is required; sparse is optional (``embed_sparse`` returns
``None`` when a backend doesn't support it, e.g. a plain dense-only model).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from chancel.stores.base import SparseVector


class Embedder(Protocol):
    """Turns text into vectors for dense (and, optionally, sparse) retrieval."""

    dense_dim: int

    def embed_dense(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        """Dense embedding, one vector of length ``dense_dim`` per input text."""
        ...

    def embed_sparse(self, texts: Sequence[str]) -> list[SparseVector] | None:
        """Sparse embedding, one per input text, or ``None`` if unsupported."""
        ...
