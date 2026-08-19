"""Contracts every store backend and storage layout must satisfy.

Two layers:

``VectorStore`` is the low-level, collection-addressed contract -- create and
drop collections, upsert points, run a query, delete by space. It knows
nothing about firm/space semantics; that is ``StorageMode``'s job, one layer
up. This is the whole surface a forker adding a new backend (pgvector,
Weaviate, ...) needs to implement.

``StorageMode`` is the layer the leak suite compares. ``isolated``,
``filtered``, and ``shared`` (see ``chancel.stores.isolated`` /
``.filtered`` / ``.shared``) each wrap a ``VectorStore`` over the same
logical vocabulary -- the firm collection plus one collection per space --
and differ *only* in how that vocabulary maps onto physical storage and how
(or whether) the boundary between spaces is enforced.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import ClassVar, Protocol

from pydantic import BaseModel

from chancel.model import DocumentId, RetrievedChunk


class SparseVector(BaseModel, frozen=True):
    """A sparse vector as parallel index/value arrays. ``len(indices) == len(values)``."""

    indices: tuple[int, ...]
    values: tuple[float, ...]


class StoredPoint(BaseModel, frozen=True):
    """One point as handed to ``VectorStore.upsert``.

    ``payload`` carries doc metadata: ``space_id``, ``scope``, ``local_id``,
    ``title``, ``text``, and (for the single-collection layouts) ``logical``.
    """

    id: str
    dense: tuple[float, ...]
    sparse: SparseVector | None = None
    payload: dict[str, str | None]


class ScoredPoint(BaseModel, frozen=True):
    """One result as handed back by ``VectorStore.query``."""

    id: str
    score: float
    payload: dict[str, str | None]


class DeletionReport(BaseModel, frozen=True):
    """Result of a delete or a deletion-verification call.

    ``independent_of_query_path`` is the load-bearing field: it records
    whether the check that produced ``deleted`` used a mechanism entirely
    outside the one ``StorageMode.search`` uses (isolated's
    ``list_collections()``) or re-ran the same query machinery under test
    (filtered's and shared's re-filtered query, which therefore cannot
    *certify* deletion -- see finding 4 in the leak suite).
    """

    space_id: str
    deleted: bool
    method: str
    independent_of_query_path: bool
    detail: str


class VectorStore(Protocol):
    """Low-level, collection-addressed vector store contract.

    Implementations: ``chancel.stores.inmemory.InMemoryStore`` (reference,
    no deps) and ``chancel.stores.qdrant.QdrantStore`` (real backend, optional
    dependency).
    """

    def create_collection(self, name: str, dense_dim: int, *, sparse: bool) -> None:
        """Create a collection. Idempotency is not guaranteed; callers provision once."""
        ...

    def drop_collection(self, name: str) -> None:
        """Drop a collection outright. Missing collections are not an error."""
        ...

    def list_collections(self) -> frozenset[str]:
        """Every collection that currently exists."""
        ...

    def upsert(self, collection: str, points: Sequence[StoredPoint]) -> None:
        """Insert or overwrite points by id."""
        ...

    def query(
        self,
        collection: str,
        dense: tuple[float, ...] | None,
        sparse: SparseVector | None,
        *,
        filter_logical: str | Sequence[str] | None = None,
        limit: int,
    ) -> list[ScoredPoint]:
        """Search one collection.

        ``dense=None`` runs a filter-only "scroll" with no ranking (score
        reported as 0.0) -- used by ``verify_deletion``, which needs to
        check for the *presence* of points, not rank them.

        ``filter_logical`` matches against the payload's ``"logical"``
        field: a single value, a sequence of values (match-any / OR), or
        ``None`` for no filter at all. The isolated layout never passes
        anything but ``None`` -- there is nothing to filter, the collection
        *is* the boundary.
        """
        ...

    def delete_by_space(self, collection: str, space_id: str) -> int:
        """Delete every point whose payload ``space_id`` matches. Returns the count deleted."""
        ...


class StorageMode(Protocol):
    """One of the three physical layouts the leak suite compares.

    Constructed over a ``VectorStore`` plus the corpus vocabulary of logical
    collections (the firm collection and one ``space-<id>`` per matter).
    """

    mode_name: ClassVar[str]

    def provision(self, space_ids: Iterable[str], dense_dim: int, sparse: bool) -> None:
        """Create whatever physical collection(s) this layout needs."""
        ...

    def ingest(
        self,
        doc: DocumentId,
        title: str,
        text: str,
        dense: tuple[float, ...],
        sparse: SparseVector | None,
    ) -> None:
        """Store one document."""
        ...

    def search(
        self,
        authorized: frozenset[str],
        dense: tuple[float, ...] | None,
        sparse: SparseVector | None,
        limit: int,
    ) -> list[RetrievedChunk]:
        """Search within exactly the logical collections named in ``authorized``.

        ``authorized`` comes from ``PolicyGate.authorize()`` -- see
        ``chancel.retriever.Retriever``, the only caller of this method.
        """
        ...

    def delete_space(self, space_id: str) -> DeletionReport:
        """Delete every document belonging to one space."""
        ...

    def verify_deletion(self, space_id: str) -> DeletionReport:
        """Independently (or not -- see the report's own field) check that a space is gone."""
        ...
