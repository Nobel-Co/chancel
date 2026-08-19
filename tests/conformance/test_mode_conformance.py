"""Conformance for the ``StorageMode`` protocol, parametrized across every
mode x store combination (``registry_conformance.MODES`` x ``STORES``).

This file asserts only the contract every ``StorageMode`` shares regardless
of its security posture -- shape, limits, deletion-report fields. It does
NOT assert isolation strength; that is ``tests/leaks/``'s job, and the
distinction matters here specifically because the three layouts do not all
meet the same contract:

**Finding, read from source (``src/chancel/stores/shared.py::SharedStore.search``):**
``isolated`` and ``filtered`` both honor an explicit ``authorized`` set --
isolated by only querying the collections named in it, filtered by passing
it straight through as ``filter_logical``. ``shared`` does not: its
``search()`` takes ``authorized`` (to satisfy the protocol) and immediately
does ``del authorized``, always querying with ``filter_logical=None``. A
firm-only ``authorized`` set is silently ignored -- this is finding 1 of the
leak suite, deliberately pinned (see ``tests/unit/test_layouts.py``'s
``test_shared_mode_can_leak_other_matter_content_by_design``), not a bug to
fix here.

So: the "search() returns list[RetrievedChunk] and honors limit" shape
contract runs across all three modes below. The "an explicit firm-only
``authorized`` set actually restricts results" contract is real for
isolated and filtered only, and is asserted only for those two --
asserting it for shared would either be testing a lie or duplicating the
leak suite's own pinned-red assertion under a different name.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _contracts import assert_deletion_report_shape
from generate_corpus import generate
from registry_conformance import MODES, STORES

from chancel.embedders.hash_stub import HashStubEmbedder
from chancel.ingest import ingest_corpus
from chancel.model import ActiveScope, RetrievedChunk
from chancel.policy import PolicyGate
from chancel.stores.base import StorageMode, VectorStore

CORPUS = generate()
SPACE_IDS = ["matter-alderman", "matter-brightwater"]

# isolated and filtered enforce `authorized`; shared ignores it entirely --
# see module docstring. Excluded here on purpose, not an oversight.
MODES_HONORING_AUTHORIZATION = ["isolated", "filtered"]


def _build_store(name: str, tmp_path: Path) -> VectorStore:
    if name == "inmemory":
        from chancel.stores.inmemory import InMemoryStore

        return InMemoryStore()
    if name == "qdrant":
        pytest.importorskip("qdrant_client")
        from chancel.stores.qdrant import QdrantStore

        return QdrantStore(tmp_path / "qdrant-mode-conformance")
    raise AssertionError(f"unknown store name: {name!r}")


def _build_mode(mode_name: str, store: VectorStore) -> StorageMode:
    if mode_name == "isolated":
        from chancel.stores.isolated import IsolatedStore

        return IsolatedStore(store)
    if mode_name == "filtered":
        from chancel.stores.filtered import FilteredStore

        return FilteredStore(store)
    if mode_name == "shared":
        from chancel.stores.shared import SharedStore

        return SharedStore(store)
    raise AssertionError(f"unknown mode name: {mode_name!r}")


def _build(mode_name: str, store_name: str, tmp_path: Path) -> tuple[StorageMode, HashStubEmbedder]:
    store = _build_store(store_name, tmp_path)
    embedder = HashStubEmbedder()
    mode = _build_mode(mode_name, store)
    ingest_corpus(mode, CORPUS, embedder)
    return mode, embedder


@pytest.mark.parametrize("store_name", STORES)
@pytest.mark.parametrize("mode_name", MODES)
def test_search_returns_retrieved_chunks_and_honors_limit(
    mode_name: str, store_name: str, tmp_path: Path
) -> None:
    mode, embedder = _build(mode_name, store_name, tmp_path)
    gate = PolicyGate(SPACE_IDS)
    scope = ActiveScope(space_id="matter-alderman")
    authorized = gate.authorize(scope, gate.default_allowlist(scope))

    dense = embedder.embed_dense(["billing time entry policy"])[0]
    results = mode.search(authorized, dense, None, limit=3)

    assert isinstance(results, list)
    assert len(results) <= 3
    for chunk in results:
        assert isinstance(chunk, RetrievedChunk)
        assert isinstance(chunk.score, float)
        assert chunk.doc_id is not None


@pytest.mark.parametrize("store_name", STORES)
@pytest.mark.parametrize("mode_name", MODES_HONORING_AUTHORIZATION)
def test_explicit_firm_only_authorization_is_honored(
    mode_name: str, store_name: str, tmp_path: Path
) -> None:
    """isolated and filtered only. See module docstring for why shared is
    excluded -- it is a real, source-verified property of shared.py, not an
    oversight."""
    mode, embedder = _build(mode_name, store_name, tmp_path)

    dense = embedder.embed_dense(["seaworthiness salvage subrogation underwriter"])[0]
    results = mode.search(frozenset({"firm"}), dense, None, limit=20)

    for chunk in results:
        assert chunk.doc_id.space_id is None, "firm-only authorization leaked a space-scoped doc"


@pytest.mark.parametrize("store_name", STORES)
@pytest.mark.parametrize("mode_name", MODES)
def test_delete_space_and_verify_deletion_report_shapes(
    mode_name: str, store_name: str, tmp_path: Path
) -> None:
    mode, _embedder = _build(mode_name, store_name, tmp_path)

    delete_report = mode.delete_space("matter-alderman")
    assert_deletion_report_shape(delete_report, "matter-alderman")

    verify_report = mode.verify_deletion("matter-alderman")
    assert_deletion_report_shape(verify_report, "matter-alderman")
