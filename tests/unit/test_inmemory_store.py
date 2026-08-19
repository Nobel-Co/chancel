"""Unit tests for the InMemoryStore reference VectorStore."""

from __future__ import annotations

from generate_corpus import generate

from chancel.embedders.hash_stub import HashStubEmbedder
from chancel.stores.base import StoredPoint
from chancel.stores.inmemory import InMemoryStore


def test_round_trip_upsert_and_query() -> None:
    store = InMemoryStore()
    store.create_collection("firm", dense_dim=4, sparse=False)
    point = StoredPoint(
        id="f1", dense=(1.0, 0.0, 0.0, 0.0), sparse=None, payload={"title": "x", "text": "y"}
    )
    store.upsert("firm", [point])

    results = store.query("firm", (1.0, 0.0, 0.0, 0.0), None, filter_logical=None, limit=5)

    assert len(results) == 1
    assert results[0].id == "f1"
    assert results[0].score == 1.0
    assert results[0].payload["title"] == "x"


def test_query_on_missing_collection_returns_empty() -> None:
    store = InMemoryStore()
    assert store.query("nope", (1.0,), None, filter_logical=None, limit=5) == []


def test_drop_and_list_collections() -> None:
    store = InMemoryStore()
    store.create_collection("firm", dense_dim=4, sparse=False)
    assert store.list_collections() == frozenset({"firm"})

    store.drop_collection("firm")

    assert store.list_collections() == frozenset()


def test_delete_by_space() -> None:
    store = InMemoryStore()
    store.create_collection("corpus", dense_dim=4, sparse=False)
    p1 = StoredPoint(
        id="a1", dense=(1.0, 0.0, 0.0, 0.0), sparse=None, payload={"space_id": "matter-alderman"}
    )
    p2 = StoredPoint(
        id="b1", dense=(0.0, 1.0, 0.0, 0.0), sparse=None, payload={"space_id": "matter-brightwater"}
    )
    store.upsert("corpus", [p1, p2])

    deleted = store.delete_by_space("corpus", "matter-alderman")

    assert deleted == 1
    remaining = store.query("corpus", None, None, filter_logical=None, limit=10)
    assert {r.id for r in remaining} == {"b1"}


def test_filter_logical_match_any() -> None:
    store = InMemoryStore()
    store.create_collection("corpus", dense_dim=2, sparse=False)
    store.upsert(
        "corpus",
        [
            StoredPoint(id="f1", dense=(1.0, 0.0), sparse=None, payload={"logical": "firm"}),
            StoredPoint(
                id="a1", dense=(1.0, 0.0), sparse=None, payload={"logical": "space-matter-alderman"}
            ),
            StoredPoint(
                id="b1",
                dense=(1.0, 0.0),
                sparse=None,
                payload={"logical": "space-matter-brightwater"},
            ),
        ],
    )

    results = store.query(
        "corpus",
        (1.0, 0.0),
        None,
        filter_logical=("firm", "space-matter-alderman"),
        limit=10,
    )

    assert {r.id for r in results} == {"f1", "a1"}


def test_cosine_ordering_ranks_relevant_doc_higher_using_hash_stub_on_real_corpus() -> None:
    corpus = generate()
    embedder = HashStubEmbedder()
    store = InMemoryStore()
    store.create_collection("mixed", dense_dim=embedder.dense_dim, sparse=False)

    # a5 "Discovery Plan" mentions both "demurrage" and "fumigation"; b1
    # "Matter Intake Memo" (brightwater) mentions neither.
    alderman_doc = next(d for d in corpus["matter-alderman"] if d["local_id"] == "a5")
    brightwater_doc = next(d for d in corpus["matter-brightwater"] if d["local_id"] == "b1")

    for tag, doc in [("alderman", alderman_doc), ("brightwater", brightwater_doc)]:
        dense = embedder.embed_dense([doc["text"]])[0]
        store.upsert(
            "mixed", [StoredPoint(id=tag, dense=dense, sparse=None, payload={"text": doc["text"]})]
        )

    query_dense = embedder.embed_dense(["demurrage fumigation"])[0]
    results = store.query("mixed", query_dense, None, filter_logical=None, limit=2)

    assert results[0].id == "alderman"
