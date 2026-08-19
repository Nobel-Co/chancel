"""Unit tests for chancel.model: the invariant is a DocumentId cannot express
an inconsistent scope, and an ActiveScope is the only source of authority.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from chancel.model import (
    FIRM_COLLECTION,
    ActiveScope,
    DocumentId,
    RetrievalReceipt,
    Scope,
    space_collection,
)

INVALID_SPACE_IDS = [
    "Firm",  # uppercase not allowed, and "firm"-like collision attempt
    "a b",  # whitespace
    "",  # empty
    "firm",  # reserved literal
    "a" * 64,  # too long (max 63)
    "UPPER",  # uppercase
    "-leading-dash",  # must start with alnum
]


class TestDocumentId:
    def test_firm_with_space_id_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DocumentId(scope=Scope.FIRM, space_id="alderman", local_id="doc-1")

    def test_space_without_space_id_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DocumentId(scope=Scope.SPACE, space_id=None, local_id="doc-1")

    @pytest.mark.parametrize("bad_space_id", INVALID_SPACE_IDS)
    def test_space_with_invalid_space_id_is_rejected(self, bad_space_id: str) -> None:
        with pytest.raises(ValidationError):
            DocumentId(scope=Scope.SPACE, space_id=bad_space_id, local_id="doc-1")

    def test_firm_scoped_constructs(self) -> None:
        doc = DocumentId(scope=Scope.FIRM, space_id=None, local_id="playbook-1")
        assert doc.collection == FIRM_COLLECTION

    def test_space_scoped_constructs(self) -> None:
        doc = DocumentId(scope=Scope.SPACE, space_id="alderman", local_id="doc-1")
        assert doc.collection == space_collection("alderman")

    def test_local_id_must_be_non_empty(self) -> None:
        with pytest.raises(ValidationError):
            DocumentId(scope=Scope.FIRM, space_id=None, local_id="")

    def test_frozen(self) -> None:
        doc = DocumentId(scope=Scope.FIRM, space_id=None, local_id="playbook-1")
        with pytest.raises(ValidationError):
            doc.local_id = "other"  # type: ignore[misc]


class TestActiveScope:
    def test_allowed_collections_exact_value(self) -> None:
        scope = ActiveScope(space_id="alderman")
        assert scope.allowed_collections == frozenset({"firm", "space-alderman"})

    @pytest.mark.parametrize("bad_space_id", INVALID_SPACE_IDS)
    def test_invalid_space_id_rejected(self, bad_space_id: str) -> None:
        with pytest.raises(ValidationError):
            ActiveScope(space_id=bad_space_id)

    def test_firm_literal_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ActiveScope(space_id="firm")

    def test_frozen(self) -> None:
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ValidationError):
            scope.space_id = "other"  # type: ignore[misc]


class TestRetrievalReceiptCanonicalJson:
    def _receipt(self, **overrides: object) -> RetrievalReceipt:
        fields: dict[str, object] = {
            "ts": "2026-08-19T00:00:00Z",
            "space_id": "alderman",
            "decision": "allow",
            "requested_collections": ("firm", "space-alderman"),
            "allowed_collections": ("firm", "space-alderman"),
            "reason": "ok",
            "query_fingerprint": "a" * 64,
            "returned_doc_ids": ("firm:playbook-1",),
            "prev_sha256": None,
        }
        fields.update(overrides)
        return RetrievalReceipt(**fields)  # type: ignore[arg-type]

    def test_same_fields_produce_identical_bytes(self) -> None:
        a = self._receipt()
        b = self._receipt()
        assert a.canonical_json() == b.canonical_json()

    def test_construction_order_of_kwargs_is_irrelevant(self) -> None:
        a = RetrievalReceipt(
            ts="2026-08-19T00:00:00Z",
            space_id="alderman",
            decision="deny",
            requested_collections=("space-brightwater",),
            allowed_collections=("firm", "space-alderman"),
            reason="requested collection outside active scope",
            query_fingerprint="b" * 64,
            returned_doc_ids=(),
        )
        b = RetrievalReceipt(
            returned_doc_ids=(),
            query_fingerprint="b" * 64,
            reason="requested collection outside active scope",
            allowed_collections=("firm", "space-alderman"),
            requested_collections=("space-brightwater",),
            decision="deny",
            space_id="alderman",
            ts="2026-08-19T00:00:00Z",
        )
        assert a.canonical_json() == b.canonical_json()

    def test_different_content_differs(self) -> None:
        a = self._receipt()
        b = self._receipt(reason="different")
        assert a.canonical_json() != b.canonical_json()

    def test_no_whitespace_variance(self) -> None:
        receipt = self._receipt()
        assert " " not in receipt.canonical_json()
        assert "\n" not in receipt.canonical_json()
