"""Single shared collection, NO filter at all. Prompt-only "isolation".

DELIBERATELY WEAK. This is what much shipped software does: one corpus,
system-prompt instructions asking the model not to cross matters, and
nothing enforcing it below that. The leak suite's finding 1 exists to catch
exactly this file, and CI asserts it stays red. Do not "fix" ``search()``
below by adding a filter -- that would just turn this into ``filtered.py``
under a different name and remove the negative example the suite needs.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from chancel.model import DocumentId, RetrievedChunk, space_collection
from chancel.stores._common import build_point, chunk_from_scored
from chancel.stores.base import DeletionReport, SparseVector, VectorStore

CORPUS_COLLECTION = "corpus"


class SharedStore:
    """StorageMode: one physical collection, unfiltered search. Weak on purpose."""

    mode_name: ClassVar[str] = "shared"

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
        # Same ingest payload as filtered.py, "logical" field included -- the
        # weakness here is entirely in search() below, not in what gets
        # written.
        point = build_point(doc, title, text, dense, sparse, logical=doc.collection)
        self._store.upsert(CORPUS_COLLECTION, [point])

    def search(
        self,
        authorized: frozenset[str],
        dense: tuple[float, ...] | None,
        sparse: SparseVector | None,
        limit: int,
    ) -> list[RetrievedChunk]:
        # `authorized` is accepted -- to satisfy the StorageMode protocol --
        # and then ignored. No filter is passed, so the whole shared
        # collection, every matter, is in play for every query. This is
        # finding 1.
        del authorized
        results = self._store.query(
            CORPUS_COLLECTION, dense, sparse, filter_logical=None, limit=limit
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
                "'corpus' collection."
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
                "test, so it cannot independently certify deletion."
            ),
        )
