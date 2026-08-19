"""Helpers shared by isolated.py, filtered.py, and shared.py.

Purely mechanical -- building a ``StoredPoint`` payload from a
``DocumentId`` and reconstructing a ``RetrievedChunk`` from a
``ScoredPoint``. None of the isolation logic lives here, so sharing it does
not blur what each layout file is individually responsible for defending
(or, in ``shared.py``'s case, deliberately failing to defend).
"""

from __future__ import annotations

from chancel.model import DocumentId, RetrievedChunk, Scope
from chancel.stores.base import ScoredPoint, SparseVector, StoredPoint


def build_payload(
    doc: DocumentId, title: str, text: str, *, logical: str | None = None
) -> dict[str, str | None]:
    payload: dict[str, str | None] = {
        "space_id": doc.space_id,
        "scope": doc.scope.value,
        "local_id": doc.local_id,
        "title": title,
        "text": text,
    }
    if logical is not None:
        payload["logical"] = logical
    return payload


def build_point(
    doc: DocumentId,
    title: str,
    text: str,
    dense: tuple[float, ...],
    sparse: SparseVector | None,
    *,
    logical: str | None = None,
) -> StoredPoint:
    return StoredPoint(
        id=f"{doc.collection}:{doc.local_id}",
        dense=dense,
        sparse=sparse,
        payload=build_payload(doc, title, text, logical=logical),
    )


def chunk_from_scored(point: ScoredPoint) -> RetrievedChunk:
    payload = point.payload
    scope_raw = payload.get("scope")
    local_id = payload.get("local_id")
    assert scope_raw is not None, "stored point missing required 'scope' payload field"
    assert local_id is not None, "stored point missing required 'local_id' payload field"
    doc_id = DocumentId(scope=Scope(scope_raw), space_id=payload.get("space_id"), local_id=local_id)
    return RetrievedChunk(doc_id=doc_id, text=payload.get("text") or "", score=point.score)
