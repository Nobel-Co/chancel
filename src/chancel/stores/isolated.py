"""One physical collection per logical collection. The claim being defended.

``search()`` queries exactly the collections named in ``authorized``, always
with ``filter_logical=None`` -- there is nothing to filter because the
collection *is* the boundary. This class has no parameter anywhere that
accepts a foreign collection or a filter: a leak test asserts that
unrepresentability by inspecting its public methods.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from chancel.model import FIRM_COLLECTION, DocumentId, RetrievedChunk, space_collection
from chancel.stores._common import build_point, chunk_from_scored
from chancel.stores.base import DeletionReport, ScoredPoint, SparseVector, VectorStore


class IsolatedStore:
    """StorageMode: one physical collection per logical collection."""

    mode_name: ClassVar[str] = "isolated"

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    def provision(self, space_ids: Iterable[str], dense_dim: int, sparse: bool) -> None:
        self._store.create_collection(FIRM_COLLECTION, dense_dim, sparse=sparse)
        for space_id in space_ids:
            self._store.create_collection(space_collection(space_id), dense_dim, sparse=sparse)

    def ingest(
        self,
        doc: DocumentId,
        title: str,
        text: str,
        dense: tuple[float, ...],
        sparse: SparseVector | None,
    ) -> None:
        point = build_point(doc, title, text, dense, sparse)
        self._store.upsert(doc.collection, [point])

    def search(
        self,
        authorized: frozenset[str],
        dense: tuple[float, ...] | None,
        sparse: SparseVector | None,
        limit: int,
    ) -> list[RetrievedChunk]:
        results: list[ScoredPoint] = []
        for collection in authorized:
            results.extend(
                self._store.query(collection, dense, sparse, filter_logical=None, limit=limit)
            )
        results.sort(key=lambda p: p.score, reverse=True)
        return [chunk_from_scored(p) for p in results[:limit]]

    def delete_space(self, space_id: str) -> DeletionReport:
        self._store.drop_collection(space_collection(space_id))
        return DeletionReport(
            space_id=space_id,
            deleted=True,
            method="drop_collection",
            independent_of_query_path=True,
            detail=(
                "Collection dropped outright; nothing to filter around because "
                "the collection was the only boundary that ever existed."
            ),
        )

    def verify_deletion(self, space_id: str) -> DeletionReport:
        gone = space_collection(space_id) not in self._store.list_collections()
        return DeletionReport(
            space_id=space_id,
            deleted=gone,
            method="list_collections",
            independent_of_query_path=True,
            detail=(
                "list_collections() is external to the query mechanism entirely -- "
                "this check runs no query at all, so nothing a query-path bug could "
                "do would be able to fool it."
            ),
        )
