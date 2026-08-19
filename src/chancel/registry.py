"""Name -> constructor registry for stores, storage layouts, providers, and embedders."""

from __future__ import annotations

import os

from chancel.embedders.base import Embedder
from chancel.providers.base import ChatModel
from chancel.stores.base import StorageMode, VectorStore
from chancel.stores.filtered import FilteredStore
from chancel.stores.inmemory import InMemoryStore
from chancel.stores.isolated import IsolatedStore
from chancel.stores.shared import SharedStore

_STORE_KINDS = ("inmemory", "qdrant")
_MODE_NAMES = ("isolated", "filtered", "shared")
_PROVIDER_NAMES = ("echo", "hostile_echo", "anthropic", "openai_compat")
_EMBEDDER_NAMES = ("hash_stub", "fastembed_local", "openai_compat")


def build_store(kind: str, location: str | None = None) -> VectorStore:
    if kind == "inmemory":
        return InMemoryStore()
    if kind == "qdrant":
        # Deferred: qdrant-client is an optional dependency, so this import
        # must not happen unless a qdrant store is actually requested.
        from chancel.stores.qdrant import QdrantStore

        return QdrantStore(location if location is not None else ":memory:")
    raise ValueError(f"unknown store kind {kind!r}; valid kinds: {', '.join(_STORE_KINDS)}")


def build_mode(mode_name: str, store: VectorStore) -> StorageMode:
    if mode_name == "isolated":
        return IsolatedStore(store)
    if mode_name == "filtered":
        return FilteredStore(store)
    if mode_name == "shared":
        return SharedStore(store)
    raise ValueError(f"unknown mode {mode_name!r}; valid modes: {', '.join(_MODE_NAMES)}")


def build_provider(
    name: str | None = None, *, model: str | None = None, base_url: str | None = None
) -> ChatModel:
    """Build a ``ChatModel`` by name.

    ``name`` defaults to ``CHANCEL_PROVIDER`` (itself defaulting to
    ``"echo"``); ``model``/``base_url`` default to ``CHANCEL_MODEL`` /
    ``CHANCEL_BASE_URL``. An explicit argument always wins over its env var.
    """
    resolved_name = name if name is not None else os.environ.get("CHANCEL_PROVIDER") or "echo"
    resolved_model = model if model is not None else os.environ.get("CHANCEL_MODEL")
    resolved_base_url = base_url if base_url is not None else os.environ.get("CHANCEL_BASE_URL")

    if resolved_name == "echo":
        from chancel.providers.echo import EchoModel

        return EchoModel()
    if resolved_name == "hostile_echo":
        # hostile_echo is built by a different agent in this same PRP; guard
        # against it not existing yet (or not yet on this branch) with a
        # clear error instead of a bare traceback.
        try:
            from chancel.providers.hostile_echo import (  # type: ignore[import-not-found]
                HostileEchoModel,
            )
        except ImportError as exc:
            raise ValueError(
                "provider 'hostile_echo' is not available: "
                "chancel.providers.hostile_echo could not be imported"
            ) from exc
        return HostileEchoModel()  # type: ignore[no-any-return]
    if resolved_name == "anthropic":
        from chancel.providers.anthropic import AnthropicModel

        return AnthropicModel(model=resolved_model)
    if resolved_name == "openai_compat":
        from chancel.providers.openai_compat import OpenAICompatModel

        return OpenAICompatModel(model=resolved_model, base_url=resolved_base_url)
    raise ValueError(
        f"unknown provider {resolved_name!r}; valid providers: {', '.join(_PROVIDER_NAMES)}"
    )


def build_embedder(name: str | None = None) -> Embedder:
    """Build an ``Embedder`` by name. Defaults to ``hash_stub``."""
    resolved_name = name or "hash_stub"

    if resolved_name == "hash_stub":
        from chancel.embedders.hash_stub import HashStubEmbedder

        return HashStubEmbedder()
    if resolved_name == "fastembed_local":
        from chancel.embedders.fastembed_local import FastEmbedLocalEmbedder

        return FastEmbedLocalEmbedder()
    if resolved_name == "openai_compat":
        from chancel.embedders.openai_compat import OpenAICompatEmbedder

        return OpenAICompatEmbedder()
    raise ValueError(
        f"unknown embedder {resolved_name!r}; valid embedders: {', '.join(_EMBEDDER_NAMES)}"
    )
