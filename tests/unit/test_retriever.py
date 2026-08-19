"""Unit tests for Retriever -- the sole StorageMode.search caller."""

from __future__ import annotations

import hashlib
import inspect

import pytest

from chancel.embedders.hash_stub import HashStubEmbedder
from chancel.exceptions import ScopeViolation
from chancel.model import ActiveScope, RetrievalReceipt
from chancel.policy import PolicyGate
from chancel.retriever import Retriever
from chancel.stores.inmemory import InMemoryStore
from chancel.stores.isolated import IsolatedStore


class _SpyAudit:
    def __init__(self) -> None:
        self.receipts: list[RetrievalReceipt] = []

    def __call__(self, receipt: RetrievalReceipt) -> None:
        self.receipts.append(receipt)


def _make_retriever(
    known_spaces: tuple[str, ...] = ("matter-alderman",),
) -> tuple[Retriever, _SpyAudit]:
    store = InMemoryStore()
    mode = IsolatedStore(store)
    embedder = HashStubEmbedder()
    mode.provision(known_spaces, embedder.dense_dim, True)
    gate = PolicyGate(known_spaces)
    audit = _SpyAudit()
    return Retriever(gate, mode, embedder, audit=audit), audit


def test_allow_path_writes_one_allow_receipt_with_correct_fields() -> None:
    retriever, audit = _make_retriever()
    scope = ActiveScope(space_id="matter-alderman")

    chunks = retriever.retrieve(scope, "contamination damages", limit=3)

    assert isinstance(chunks, list)
    assert len(audit.receipts) == 1
    receipt = audit.receipts[0]
    assert receipt.decision == "allow"
    assert receipt.space_id == "matter-alderman"
    assert set(receipt.allowed_collections) == {"firm", "space-matter-alderman"}
    assert set(receipt.requested_collections) == {"firm", "space-matter-alderman"}
    assert receipt.reason == "authorized"
    assert receipt.query_fingerprint == hashlib.sha256(b"contamination damages").hexdigest()
    assert receipt.returned_doc_ids == tuple(chunk.doc_id.local_id for chunk in chunks)


def test_deny_path_writes_one_deny_receipt_and_reraises() -> None:
    retriever, audit = _make_retriever(known_spaces=("matter-alderman",))
    unknown_scope = ActiveScope(space_id="matter-unknown")

    with pytest.raises(ScopeViolation):
        retriever.retrieve(unknown_scope, "anything")

    assert len(audit.receipts) == 1
    receipt = audit.receipts[0]
    assert receipt.decision == "deny"
    assert receipt.space_id == "matter-unknown"
    assert receipt.reason == "unknown space"


def test_no_audit_callback_is_fine() -> None:
    store = InMemoryStore()
    mode = IsolatedStore(store)
    embedder = HashStubEmbedder()
    mode.provision(["matter-alderman"], embedder.dense_dim, True)
    gate = PolicyGate(["matter-alderman"])
    retriever = Retriever(gate, mode, embedder)  # no audit callback

    scope = ActiveScope(space_id="matter-alderman")
    result = retriever.retrieve(scope, "anything")
    assert result == []


def test_retrieve_signature_has_no_collection_or_filter_parameter() -> None:
    params = dict(inspect.signature(Retriever.retrieve).parameters)
    params.pop("self", None)
    assert set(params) == {"scope", "query", "limit"}
