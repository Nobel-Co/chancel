"""Conformance for the ``Embedder`` protocol, parametrized across every
registered embedder (``registry_conformance.EMBEDDERS_OFFLINE`` +
``EMBEDDERS_OPTIONAL``).

``hash_stub`` is stdlib-only and runs everywhere. ``fastembed_local``
downloads model weights on first use, so it is ``importorskip``-guarded on
the ``fastembed`` package itself -- if the extra isn't installed, it is
skipped rather than attempting a download. ``openai_compat`` has a real SDK
dependency; like the chat-model adapters, it accepts an injected HTTP
client, so it is driven over a mocked ``httpx2`` transport whose handler
computes a deterministic, vocabulary-sensitive vector per input text (so the
similarity-ordering assertion is actually exercising something, not just
echoing one fixed vector for every input). No network, no key.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest
from _contracts import (
    assert_dense_shape,
    assert_deterministic_dense,
    assert_similarity_ordering,
    assert_sparse_contract,
)
from registry_conformance import EMBEDDERS_OFFLINE, EMBEDDERS_OPTIONAL

# Deliberately disjoint vocabulary: A and B share four content words
# (hull, seaworthiness, marine, casualty); DISSIMILAR shares none of them.
SIMILAR_A = "hull seaworthiness marine casualty vessel damage"
SIMILAR_B = "seaworthiness hull casualty marine claim underwriter"
DISSIMILAR = "billing timesheet invoice partner associate paralegal"

ALL_NAMES = [*EMBEDDERS_OFFLINE, *EMBEDDERS_OPTIONAL]


def _mock_openai_embed_client(dim: int) -> Any:
    """An httpx2 client whose handler parses the real request body and
    returns a deterministic, token-overlap-sensitive vector per input text
    -- so this drives ``OpenAICompatEmbedder.embed_dense``'s actual response
    parsing, not a stub that bypasses it."""
    httpx2 = pytest.importorskip("httpx2")
    from chancel.embedders.hash_stub import _token_unit_vector, _tokenize

    def _vector_for(text: str) -> list[float]:
        tokens = _tokenize(text)
        if not tokens:
            return [0.0] * dim
        accum = [0.0] * dim
        for token in tokens:
            unit = _token_unit_vector(token, dim)
            for i in range(dim):
                accum[i] += unit[i]
        norm = math.sqrt(sum(v * v for v in accum)) or 1.0
        return [v / norm for v in accum]

    def handler(request: Any) -> Any:
        body = json.loads(request.content)
        inputs = body["input"]
        data = [
            {"object": "embedding", "index": i, "embedding": _vector_for(text)}
            for i, text in enumerate(inputs)
        ]
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "data": data,
                "model": body["model"],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    return httpx2.Client(transport=httpx2.MockTransport(handler))


def _build(name: str) -> Any:
    if name == "hash_stub":
        from chancel.embedders.hash_stub import HashStubEmbedder

        return HashStubEmbedder()
    if name == "fastembed_local":
        pytest.importorskip("fastembed")
        from chancel.embedders.fastembed_local import FastEmbedLocalEmbedder

        return FastEmbedLocalEmbedder()
    if name == "openai_compat":
        pytest.importorskip("openai")
        from chancel.embedders.openai_compat import OpenAICompatEmbedder

        dim = 16
        client = _mock_openai_embed_client(dim)
        return OpenAICompatEmbedder(
            model="text-embedding-3-small", api_key="test", dim=dim, http_client=client
        )
    raise AssertionError(f"unknown embedder name: {name!r}")


@pytest.mark.parametrize("name", ALL_NAMES)
def test_dense_shape(name: str) -> None:
    embedder = _build(name)
    assert_dense_shape(embedder, [SIMILAR_A, SIMILAR_B, DISSIMILAR])


@pytest.mark.parametrize("name", ALL_NAMES)
def test_deterministic(name: str) -> None:
    embedder = _build(name)
    assert_deterministic_dense(embedder, SIMILAR_A)


@pytest.mark.parametrize("name", ALL_NAMES)
def test_similarity_ordering(name: str) -> None:
    embedder = _build(name)
    assert_similarity_ordering(embedder, SIMILAR_A, SIMILAR_B, DISSIMILAR)


@pytest.mark.parametrize("name", ALL_NAMES)
def test_sparse_contract(name: str) -> None:
    embedder = _build(name)
    assert_sparse_contract(embedder, [SIMILAR_A, DISSIMILAR])
