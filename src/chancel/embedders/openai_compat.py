"""``Embedder`` over the OpenAI embeddings endpoint.

Optional dependency: ``pip install chancel[openai]``. Dense only --
``embed_sparse`` always returns ``None``, per the ``Embedder`` protocol's
documented behavior for backends without sparse support. Default model is
``text-embedding-3-small`` (dimension 1536); override via the constructor,
``CHANCEL_EMBED_MODEL``, and ``dim`` if a non-default model changes the
output dimension.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from chancel.stores.base import SparseVector

DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIM = 1536


class OpenAICompatEmbedder:
    """Dense-only ``Embedder`` over the OpenAI-compatible embeddings API."""

    dense_dim: int

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        dim: int | None = None,
        http_client: Any | None = None,
    ) -> None:
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "the openai_compat embedder requires the 'openai' package; "
                "install it with `pip install chancel[openai]`"
            ) from exc

        self.model = model or os.environ.get("CHANCEL_EMBED_MODEL") or DEFAULT_MODEL
        self.dense_dim = dim if dim is not None else DEFAULT_DIM
        resolved_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        resolved_base_url = base_url if base_url is not None else os.environ.get("CHANCEL_BASE_URL")

        client_kwargs: dict[str, Any] = {"api_key": resolved_key}
        if resolved_base_url is not None:
            client_kwargs["base_url"] = resolved_base_url
        if http_client is not None:
            client_kwargs["http_client"] = http_client
        self._client = openai.OpenAI(**client_kwargs)

    def embed_dense(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        response = self._client.embeddings.create(model=self.model, input=list(texts))
        return [tuple(float(x) for x in item.embedding) for item in response.data]

    def embed_sparse(self, texts: Sequence[str]) -> list[SparseVector] | None:
        del texts
        return None
