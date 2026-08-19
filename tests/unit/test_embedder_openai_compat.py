"""Smoke test for the openai_compat Embedder. No network, no key."""

from __future__ import annotations

from typing import Any

import pytest

openai = pytest.importorskip("openai")
httpx2 = pytest.importorskip("httpx2")

from chancel.embedders.openai_compat import OpenAICompatEmbedder  # noqa: E402


def test_embed_dense_returns_tuples_from_response_data() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "model": "text-embedding-3-small",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
                    {"object": "embedding", "index": 1, "embedding": [0.4, 0.5, 0.6]},
                ],
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            },
        )

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    embedder = OpenAICompatEmbedder(api_key="test", http_client=client)

    vectors = embedder.embed_dense(["hello", "world"])

    assert vectors == [(0.1, 0.2, 0.3), (0.4, 0.5, 0.6)]
    assert all(isinstance(v, tuple) for v in vectors)


def test_embed_sparse_is_always_none() -> None:
    embedder = OpenAICompatEmbedder.__new__(OpenAICompatEmbedder)  # skip __init__/client setup
    result: Any = embedder.embed_sparse(["hello"])
    assert result is None


def test_dense_dim_defaults_to_1536_and_can_be_overridden() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"object": "list", "data": [], "model": "x"})

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    default_embedder = OpenAICompatEmbedder(api_key="test", http_client=client)
    assert default_embedder.dense_dim == 1536

    custom_embedder = OpenAICompatEmbedder(api_key="test", dim=256, http_client=client)
    assert custom_embedder.dense_dim == 256
