"""Conformance for the ``VectorStore`` protocol, parametrized across every
registered store (``registry_conformance.STORES``).

``inmemory`` needs nothing. ``qdrant`` is ``importorskip``-guarded on
``qdrant-client`` and built over ``tmp_path`` -- local-mode Qdrant holds a
filesystem lock per path, so each test gets its own directory (see
``PRPs/prp-12-scope-isolation.md``'s "known gotchas").

Vectors are built with ``HashStubEmbedder`` (dense_dim 64, stdlib-only) so
no model download is needed; collections are created with that same
``dense_dim`` throughout.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _contracts import (
    assert_collection_lifecycle,
    assert_delete_by_space_scopes_correctly,
    assert_filter_logical_restricts,
    assert_query_limit_is_honored,
    assert_upsert_query_roundtrip,
)
from registry_conformance import STORES

from chancel.embedders.hash_stub import HashStubEmbedder
from chancel.stores.base import VectorStore

DENSE_DIM = HashStubEmbedder.dense_dim


def _build_store(name: str, tmp_path: Path) -> VectorStore:
    if name == "inmemory":
        from chancel.stores.inmemory import InMemoryStore

        return InMemoryStore()
    if name == "qdrant":
        pytest.importorskip("qdrant_client")
        from chancel.stores.qdrant import QdrantStore

        return QdrantStore(tmp_path / "qdrant-store-conformance")
    raise AssertionError(f"unknown store name: {name!r}")


@pytest.fixture
def embedder() -> HashStubEmbedder:
    return HashStubEmbedder()


@pytest.mark.parametrize("name", STORES)
def test_collection_lifecycle(name: str, tmp_path: Path) -> None:
    store = _build_store(name, tmp_path)
    assert_collection_lifecycle(store, "conformance-lifecycle", DENSE_DIM)


@pytest.mark.parametrize("name", STORES)
def test_upsert_then_query_roundtrips_payload(
    name: str, tmp_path: Path, embedder: HashStubEmbedder
) -> None:
    store = _build_store(name, tmp_path)
    assert_upsert_query_roundtrip(store, "conformance-roundtrip", DENSE_DIM, embedder)


@pytest.mark.parametrize("name", STORES)
def test_query_limit_is_honored(name: str, tmp_path: Path, embedder: HashStubEmbedder) -> None:
    store = _build_store(name, tmp_path)
    assert_query_limit_is_honored(store, "conformance-limit", DENSE_DIM, embedder)


@pytest.mark.parametrize("name", STORES)
def test_filter_logical_restricts_results(
    name: str, tmp_path: Path, embedder: HashStubEmbedder
) -> None:
    store = _build_store(name, tmp_path)
    assert_filter_logical_restricts(store, "conformance-filter", DENSE_DIM, embedder)


@pytest.mark.parametrize("name", STORES)
def test_delete_by_space_scopes_to_one_space(
    name: str, tmp_path: Path, embedder: HashStubEmbedder
) -> None:
    store = _build_store(name, tmp_path)
    assert_delete_by_space_scopes_correctly(store, "conformance-delete", DENSE_DIM, embedder)
