"""Integration tests against a real (local-mode) Qdrant instance.

Skips entirely if qdrant-client isn't installed (`uv sync --extra qdrant`).
Each test gets its own tmp_path because local mode holds a filesystem lock
per path (see PRPs/ai_docs/qdrant-client.md).
"""

from __future__ import annotations

import pytest

qdrant_client = pytest.importorskip("qdrant_client")

from generate_corpus import generate  # noqa: E402

from chancel.embedders.hash_stub import HashStubEmbedder  # noqa: E402
from chancel.ingest import ingest_corpus  # noqa: E402
from chancel.model import ActiveScope  # noqa: E402
from chancel.policy import PolicyGate  # noqa: E402
from chancel.stores.base import StoredPoint  # noqa: E402
from chancel.stores.filtered import FilteredStore  # noqa: E402
from chancel.stores.isolated import IsolatedStore  # noqa: E402
from chancel.stores.qdrant import QdrantStore  # noqa: E402

SPACE_IDS = ["matter-alderman", "matter-brightwater"]


@pytest.fixture
def store(tmp_path):  # type: ignore[no-untyped-def]
    return QdrantStore(tmp_path / "qdrant-data")


def test_round_trip(store: QdrantStore) -> None:
    store.create_collection("firm", dense_dim=8, sparse=False)
    dense = (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    point = StoredPoint(id="f1", dense=dense, sparse=None, payload={"title": "x"})

    store.upsert("firm", [point])
    results = store.query("firm", dense, None, filter_logical=None, limit=5)

    assert len(results) == 1
    assert results[0].payload["title"] == "x"


def test_delete_and_list_collections(store: QdrantStore) -> None:
    store.create_collection("firm", dense_dim=4, sparse=False)
    assert "firm" in store.list_collections()

    store.drop_collection("firm")

    assert "firm" not in store.list_collections()


def test_isolated_layout_over_qdrant(store: QdrantStore) -> None:
    embedder = HashStubEmbedder()
    mode = IsolatedStore(store)
    corpus = generate()
    ingest_corpus(mode, corpus, embedder)

    gate = PolicyGate(SPACE_IDS)
    scope = ActiveScope(space_id="matter-alderman")
    authorized = gate.authorize(scope, gate.default_allowlist(scope))

    dense = embedder.embed_dense(["demurrage fumigation contamination"])[0]
    results = mode.search(authorized, dense, None, limit=20)

    assert results
    for chunk in results:
        assert chunk.doc_id.space_id in (None, "matter-alderman")


def test_filtered_layout_over_qdrant(store: QdrantStore) -> None:
    embedder = HashStubEmbedder()
    mode = FilteredStore(store)
    corpus = generate()
    ingest_corpus(mode, corpus, embedder)

    gate = PolicyGate(SPACE_IDS)
    scope = ActiveScope(space_id="matter-alderman")
    authorized = gate.authorize(scope, gate.default_allowlist(scope))

    dense = embedder.embed_dense(["demurrage fumigation contamination"])[0]
    results = mode.search(authorized, dense, None, limit=20)

    assert results
    for chunk in results:
        assert chunk.doc_id.space_id in (None, "matter-alderman")


def test_filtered_layout_delete_and_verify_over_qdrant(store: QdrantStore) -> None:
    embedder = HashStubEmbedder()
    mode = FilteredStore(store)
    corpus = generate()
    ingest_corpus(mode, corpus, embedder)

    report = mode.delete_space("matter-alderman")
    assert report.deleted is True

    verify = mode.verify_deletion("matter-alderman")
    assert verify.deleted is True
    assert verify.independent_of_query_path is False


def test_modifier_idf_accepted_by_local_mode(store: QdrantStore) -> None:
    from qdrant_client import models

    if not (hasattr(models, "Modifier") and hasattr(models.Modifier, "IDF")):
        pytest.skip("qdrant_client.models.Modifier.IDF not present in this qdrant-client version")

    # Accepting the config at collection-creation time is what this test
    # verifies; it does not independently confirm per-shard IDF computation
    # behavior at query time (see the design notes returned with this PRP).
    store.create_collection("sparse-check", dense_dim=4, sparse=True)

    assert "sparse-check" in store.list_collections()
