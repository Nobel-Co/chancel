"""Smoke test for the fastembed_local Embedder.

Skipped whenever ``fastembed`` isn't installed (the ``local`` extra is
deliberately not part of the light validation environment for this layer,
since fastembed downloads model weights on first use). Real coverage of
this adapter runs wherever the ``local`` extra is installed, e.g. the
conformance tier.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastembed")

from chancel.embedders.fastembed_local import DENSE_DIM, FastEmbedLocalEmbedder


def test_embed_dense_matches_declared_dimension() -> None:
    embedder = FastEmbedLocalEmbedder()

    vectors = embedder.embed_dense(["contamination damages", "citation style guide"])

    assert len(vectors) == 2
    assert all(len(v) == DENSE_DIM == embedder.dense_dim for v in vectors)


def test_embed_sparse_returns_sparse_vectors() -> None:
    embedder = FastEmbedLocalEmbedder()

    vectors = embedder.embed_sparse(["contamination damages"])

    assert vectors is not None
    assert len(vectors) == 1
    assert len(vectors[0].indices) == len(vectors[0].values)
