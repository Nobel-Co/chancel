"""Shared conformance assertion helpers.

Every parametrized suite in this directory (``test_chatmodel_conformance.py``,
``test_embedder_conformance.py``, ``test_store_conformance.py``,
``test_mode_conformance.py``) and the meta-test
(``test_new_adapter_is_drop_in.py``) call *these* functions against a
constructed adapter instance, rather than each writing its own asserts
inline. That is what makes the meta-test a real proof rather than a
restatement: a brand-new ``ChatModel``/``Embedder`` defined entirely outside
``chancel.registry`` and outside ``registry_conformance.py`` is checked by
the identical code path a registered adapter is checked by. If the two
diverged, passing the meta-test would prove nothing about passing the real
suites.

Every function here takes an already-constructed instance -- it knows
nothing about registries, names, or how to build one. That construction
detail lives in each test file's own ``_build_*`` helper, which is the part
that legitimately differs per adapter kind (an ``openai_compat`` chat model
needs a mocked ``httpx2`` client; a ``qdrant`` store needs a ``tmp_path``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from chancel.embedders.base import Embedder
from chancel.providers.base import ChatModel, ChatTurn, ModelReply, ToolSpec
from chancel.stores.base import DeletionReport, StoredPoint, VectorStore

# ---------------------------------------------------------------------------
# ChatModel
# ---------------------------------------------------------------------------


def assert_chatmodel_shape(model: ChatModel) -> None:
    """``name`` is a non-empty ``str``."""
    assert isinstance(model.name, str)
    assert model.name


def assert_complete_contract(
    model: ChatModel, system: str, turns: Sequence[ChatTurn], tools: Sequence[ToolSpec]
) -> ModelReply:
    """``complete()`` returns a well-shaped ``ModelReply``."""
    reply = model.complete(system, turns, tools)
    assert isinstance(reply, ModelReply)
    assert isinstance(reply.text, str)
    assert isinstance(reply.tool_calls, tuple)
    return reply


def assert_tool_calls_well_formed(reply: ModelReply, offered_tool_names: set[str]) -> None:
    """Given a reply to a round that offered ``offered_tool_names``: either a
    text answer (empty ``tool_calls`` is a legal response to an offered
    tool) or every ``ToolCall`` names an offered tool and carries
    ``id: str``, ``name: str``, and ``arguments: dict`` -- never a raw
    string, per the malformed-input contract in ``chancel.providers.base``.
    """
    if not reply.tool_calls:
        assert isinstance(reply.text, str)
        return
    for call in reply.tool_calls:
        assert isinstance(call.id, str) and call.id
        assert isinstance(call.name, str) and call.name
        assert call.name in offered_tool_names, (
            f"tool_call named {call.name!r}, not among offered tools {offered_tool_names!r}"
        )
        assert isinstance(call.arguments, dict)


def assert_idempotent(
    model: ChatModel, system: str, turns: Sequence[ChatTurn], tools: Sequence[ToolSpec]
) -> None:
    """Same inputs, called twice, produce the same ``ModelReply``. Only
    meaningful for deterministic providers -- callers choose when to call
    this."""
    first = model.complete(system, turns, tools)
    second = model.complete(system, turns, tools)
    assert first == second


# ---------------------------------------------------------------------------
# Embedder
# ---------------------------------------------------------------------------


def assert_dense_shape(embedder: Embedder, texts: Sequence[str]) -> list[tuple[float, ...]]:
    """``dense_dim`` is a positive int; ``embed_dense`` returns one vector of
    that length per input text."""
    assert isinstance(embedder.dense_dim, int)
    assert embedder.dense_dim > 0

    vectors = embedder.embed_dense(texts)
    assert len(vectors) == len(texts)
    for vector in vectors:
        assert isinstance(vector, tuple)
        assert len(vector) == embedder.dense_dim
        for component in vector:
            assert isinstance(component, float)
    return vectors


def assert_deterministic_dense(embedder: Embedder, text: str) -> None:
    """Embedding the same text twice is identical."""
    first = embedder.embed_dense([text])[0]
    second = embedder.embed_dense([text])[0]
    assert first == second


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def assert_similarity_ordering(
    embedder: Embedder, similar_a: str, similar_b: str, dissimilar: str
) -> None:
    """Two texts sharing vocabulary score at least as similar to each other,
    by cosine similarity, as either scores to an unrelated third text."""
    vec_a, vec_b, vec_d = embedder.embed_dense([similar_a, similar_b, dissimilar])
    sim_related = _cosine(vec_a, vec_b)
    sim_unrelated = _cosine(vec_a, vec_d)
    assert sim_related >= sim_unrelated, (
        f"expected related texts to score >= unrelated: {sim_related} < {sim_unrelated}"
    )


def assert_sparse_contract(embedder: Embedder, texts: Sequence[str]) -> None:
    """``embed_sparse`` returns either ``None`` or one ``SparseVector`` per
    input, with parallel ``indices``/``values``, and reports support
    consistently across calls (never ``None`` once, populated the next)."""
    first = embedder.embed_sparse(texts)
    second = embedder.embed_sparse(texts)
    assert (first is None) == (second is None), "sparse support must be reported consistently"
    if first is None:
        return
    assert len(first) == len(texts)
    for sparse_vector in first:
        assert len(sparse_vector.indices) == len(sparse_vector.values)


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------


def assert_collection_lifecycle(store: VectorStore, name: str, dense_dim: int) -> None:
    """create -> appears in list_collections(); drop -> disappears."""
    store.create_collection(name, dense_dim, sparse=False)
    listing = store.list_collections()
    assert isinstance(listing, frozenset)
    assert name in listing

    store.drop_collection(name)
    assert name not in store.list_collections()


def assert_upsert_query_roundtrip(
    store: VectorStore, collection: str, dense_dim: int, embedder: Embedder
) -> None:
    """Upsert one point, query for it back, and check the payload -- text,
    title, and space_id -- round-trips faithfully; score is a float."""
    store.create_collection(collection, dense_dim, sparse=False)
    text = "conformance roundtrip probe document"
    dense = embedder.embed_dense([text])[0]
    point = StoredPoint(
        id="probe-1",
        dense=dense,
        payload={"text": text, "title": "Probe", "space_id": "matter-alderman"},
    )
    store.upsert(collection, [point])

    results = store.query(collection, dense, None, limit=5)
    assert results, "expected the just-upserted point back"
    top = results[0]
    assert isinstance(top.score, float)
    assert top.payload.get("text") == text
    assert top.payload.get("title") == "Probe"
    assert top.payload.get("space_id") == "matter-alderman"


def assert_query_limit_is_honored(
    store: VectorStore, collection: str, dense_dim: int, embedder: Embedder
) -> None:
    """``limit`` caps the number of results even when more candidates exist."""
    store.create_collection(collection, dense_dim, sparse=False)
    texts = [f"document number {i} about maritime salvage claims" for i in range(5)]
    vectors = embedder.embed_dense(texts)
    points = [
        StoredPoint(
            id=f"doc-{i}", dense=vector, payload={"text": text, "title": f"D{i}", "space_id": None}
        )
        for i, (text, vector) in enumerate(zip(texts, vectors, strict=True))
    ]
    store.upsert(collection, points)

    query_vector = embedder.embed_dense(["maritime salvage"])[0]
    results = store.query(collection, query_vector, None, limit=2)
    assert len(results) == 2


def assert_filter_logical_restricts(
    store: VectorStore, collection: str, dense_dim: int, embedder: Embedder
) -> None:
    """``filter_logical`` restricts results to the matching logical value; no
    filter at all searches across values.

    Identified by payload, not by ``ScoredPoint.id``: ``VectorStore.query()``
    does not guarantee the returned ``id`` echoes the ``StoredPoint.id`` an
    adapter was given -- ``QdrantStore`` deliberately remaps ids to
    deterministic UUIDs (Qdrant point ids must be an int or UUID; see
    ``chancel.stores.qdrant``'s module docstring), while ``InMemoryStore``
    happens to preserve them. The payload is what every ``StorageMode``
    layout actually reconstructs a ``RetrievedChunk`` from (see
    ``chancel.stores._common.chunk_from_scored``), so that is the
    cross-backend-stable identity to assert on here.
    """
    store.create_collection(collection, dense_dim, sparse=False)
    text_firm = "firm-wide billing and time-entry policy notice"
    text_space = "matter alderman filing deadline policy notice"
    vec_firm = embedder.embed_dense([text_firm])[0]
    vec_space = embedder.embed_dense([text_space])[0]
    store.upsert(
        collection,
        [
            StoredPoint(
                id="firm-doc",
                dense=vec_firm,
                payload={"text": text_firm, "title": "Firm", "space_id": None, "logical": "firm"},
            ),
            StoredPoint(
                id="space-doc",
                dense=vec_space,
                payload={
                    "text": text_space,
                    "title": "Space",
                    "space_id": "matter-alderman",
                    "logical": "space-matter-alderman",
                },
            ),
        ],
    )

    query_vector = embedder.embed_dense(["policy notice"])[0]

    filtered = store.query(collection, query_vector, None, filter_logical="firm", limit=10)
    assert all(r.payload.get("logical") == "firm" for r in filtered)
    filtered_texts = {r.payload.get("text") for r in filtered}
    assert text_firm in filtered_texts
    assert text_space not in filtered_texts

    unfiltered = store.query(collection, query_vector, None, filter_logical=None, limit=10)
    unfiltered_texts = {r.payload.get("text") for r in unfiltered}
    assert {text_firm, text_space} <= unfiltered_texts


def assert_delete_by_space_scopes_correctly(
    store: VectorStore, collection: str, dense_dim: int, embedder: Embedder
) -> None:
    """``delete_by_space`` removes only points whose payload ``space_id``
    matches, verified by re-querying and inspecting the surviving payloads'
    ``space_id`` (not ``ScoredPoint.id`` -- see
    ``assert_filter_logical_restricts`` for why id is not a cross-backend-
    stable handle)."""
    store.create_collection(collection, dense_dim, sparse=False)
    vector = embedder.embed_dense(["shared collection payload probe"])[0]
    store.upsert(
        collection,
        [
            StoredPoint(
                id="s1",
                dense=vector,
                payload={"text": "s1", "title": "S1", "space_id": "matter-alderman"},
            ),
            StoredPoint(
                id="s2",
                dense=vector,
                payload={"text": "s2", "title": "S2", "space_id": "matter-brightwater"},
            ),
        ],
    )

    deleted_count = store.delete_by_space(collection, "matter-alderman")
    assert deleted_count == 1

    remaining = store.query(collection, vector, None, limit=10)
    remaining_space_ids = {r.payload.get("space_id") for r in remaining}
    assert "matter-alderman" not in remaining_space_ids
    assert "matter-brightwater" in remaining_space_ids


# ---------------------------------------------------------------------------
# StorageMode
# ---------------------------------------------------------------------------


def assert_deletion_report_shape(report: DeletionReport, space_id: str) -> None:
    """A ``DeletionReport`` (from ``delete_space`` or ``verify_deletion``)
    carries its documented fields with the documented types."""
    assert report.space_id == space_id
    assert isinstance(report.deleted, bool)
    assert isinstance(report.method, str) and report.method
    assert isinstance(report.independent_of_query_path, bool)
    assert isinstance(report.detail, str) and report.detail
