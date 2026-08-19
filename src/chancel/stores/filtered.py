"""Single shared collection, must-filter every query. The vendor-default pattern.

Qdrant's own multitenancy guidance is to prefer this over collection-per-
tenant at scale (see ``PRPs/ai_docs/qdrant-multitenancy.md``), and it names
strict regulatory/compliance isolation as the exception a law firm's matters
fall into. This file is where that trade-off is paid for: the boundary is a
filter computed at query time, not a physical fact about storage.

Every point lives in one physical collection, ``"corpus"``. Firm docs carry
payload ``space_id=None``; a bare ``space_id`` sentinel can't distinguish
"firm" from "no filter at all", so every point also carries a ``"logical"``
field holding the logical collection name it belongs to (``"firm"`` or
``"space-<id>"``), and filtering happens on that field.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from chancel.model import DocumentId, RetrievedChunk, space_collection
from chancel.stores._common import build_point, chunk_from_scored
from chancel.stores.base import DeletionReport, SparseVector, VectorStore

CORPUS_COLLECTION = "corpus"


class FilteredStore:
    """StorageMode: one physical collection, payload-filtered per query."""

    mode_name: ClassVar[str] = "filtered"

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    def provision(self, space_ids: Iterable[str], dense_dim: int, sparse: bool) -> None:
        del space_ids  # every space shares the one physical collection
        self._store.create_collection(CORPUS_COLLECTION, dense_dim, sparse=sparse)

    def ingest(
        self,
        doc: DocumentId,
        title: str,
        text: str,
        dense: tuple[float, ...],
        sparse: SparseVector | None,
    ) -> None:
        point = build_point(doc, title, text, dense, sparse, logical=doc.collection)
        self._store.upsert(CORPUS_COLLECTION, [point])

    def search(
        self,
        authorized: frozenset[str],
        dense: tuple[float, ...] | None,
        sparse: SparseVector | None,
        limit: int,
    ) -> list[RetrievedChunk]:
        # This translation is where the freedom the isolated layout makes
        # unrepresentable gets reintroduced: a one-line mistake here (or one
        # forgotten filter anywhere else in a codebase built on this
        # pattern) is a cross-tenant read. The leak suite's findings 2-4 all
        # live in this file on purpose.
        logical_values = tuple(sorted(authorized))
        results = self._store.query(
            CORPUS_COLLECTION, dense, sparse, filter_logical=logical_values, limit=limit
        )
        return [chunk_from_scored(p) for p in results[:limit]]

    def delete_space(self, space_id: str) -> DeletionReport:
        count = self._store.delete_by_space(CORPUS_COLLECTION, space_id)
        return DeletionReport(
            space_id=space_id,
            deleted=count > 0,
            method="delete_by_space",
            independent_of_query_path=False,
            detail=(
                f"Deleted {count} point(s) via a filtered delete over the shared "
                "'corpus' collection -- the same collection every query shares."
            ),
        )

    def verify_deletion(self, space_id: str) -> DeletionReport:
        remaining = self._store.query(
            CORPUS_COLLECTION, None, None, filter_logical=space_collection(space_id), limit=1
        )
        gone = len(remaining) == 0
        return DeletionReport(
            space_id=space_id,
            deleted=gone,
            method="filtered_query",
            independent_of_query_path=False,
            detail=(
                "This check re-runs a filtered query against the mechanism under "
                "test (the same store.query + filter_logical path search() uses), "
                "so it cannot independently certify deletion -- see finding 4."
            ),
        )
