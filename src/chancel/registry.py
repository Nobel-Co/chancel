"""Name -> constructor registry for stores and storage layouts.

Provider registries (chat models, embedders) arrive in a later phase; they
will register alongside ``build_store``/``build_mode`` here.
"""

from __future__ import annotations

from chancel.stores.base import StorageMode, VectorStore
from chancel.stores.filtered import FilteredStore
from chancel.stores.inmemory import InMemoryStore
from chancel.stores.isolated import IsolatedStore
from chancel.stores.shared import SharedStore

_STORE_KINDS = ("inmemory", "qdrant")
_MODE_NAMES = ("isolated", "filtered", "shared")


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
