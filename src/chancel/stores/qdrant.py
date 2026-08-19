"""``VectorStore`` over qdrant-client, same protocol as ``InMemoryStore``.

qdrant-client is an optional dependency (``pip install chancel[qdrant]``);
the import is guarded inside this module's functions so importing sibling
modules (``inmemory.py``, ``isolated.py``, ``filtered.py``, ``shared.py``,
``chancel.retriever``, ...) never touches ``qdrant_client`` at all, and a
base install without the extra fails only if this module is actually used,
with a message naming the extra.

Uses named vectors: dense as ``"dense"``, sparse (when enabled) as
``"sparse"``. A keyword payload index is created on both ``"space_id"`` (the
raw per-document tenant key -- see ``PRPs/ai_docs/qdrant-multitenancy.md``'s
``is_tenant`` guidance) and ``"logical"`` (the field the single-collection
layouts actually filter on; see ``chancel.stores.filtered``). ``dense=None``
queries use ``scroll`` instead of ``query_points`` -- a pure filter lookup
with no ranking, used by ``verify_deletion``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from chancel.stores.base import ScoredPoint, SparseVector, StoredPoint

if TYPE_CHECKING:
    from qdrant_client import QdrantClient

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


def _load_qdrant() -> tuple[Any, Any]:
    try:
        import qdrant_client as qc
        from qdrant_client import models
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(
            "chancel.stores.qdrant requires qdrant-client. Install it with: "
            "pip install chancel[qdrant]"
        ) from exc
    return qc, models


def _build_filter(models: Any, filter_logical: str | Sequence[str] | None) -> Any:
    if filter_logical is None:
        return None
    values = [filter_logical] if isinstance(filter_logical, str) else list(filter_logical)
    return models.Filter(
        must=[models.FieldCondition(key="logical", match=models.MatchAny(any=values))]
    )


class QdrantStore:
    """``VectorStore`` backed by a real (or local-mode) Qdrant instance.

    ``location`` is ``":memory:"`` or a filesystem path, passed straight to
    ``QdrantClient`` for local mode. Local mode holds a filesystem lock per
    path, so tests give each instance its own ``tmp_path``.
    """

    def __init__(self, location: str | Path) -> None:
        qc, models = _load_qdrant()
        self._models = models
        location_str = str(location)
        self._client: QdrantClient = (
            qc.QdrantClient(":memory:")
            if location_str == ":memory:"
            else qc.QdrantClient(path=location_str)
        )

    def create_collection(self, name: str, dense_dim: int, *, sparse: bool) -> None:
        models = self._models
        vectors_config = {
            DENSE_VECTOR_NAME: models.VectorParams(size=dense_dim, distance=models.Distance.COSINE)
        }
        sparse_vectors_config = None
        if sparse:
            sparse_kwargs: dict[str, Any] = {}
            modifier = getattr(models, "Modifier", None)
            if modifier is not None and hasattr(modifier, "IDF"):
                sparse_kwargs["modifier"] = modifier.IDF
            sparse_vectors_config = {SPARSE_VECTOR_NAME: models.SparseVectorParams(**sparse_kwargs)}

        self._client.create_collection(
            collection_name=name,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_vectors_config,
        )
        self._client.create_payload_index(
            collection_name=name,
            field_name="space_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        self._client.create_payload_index(
            collection_name=name,
            field_name="logical",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

    def drop_collection(self, name: str) -> None:
        self._client.delete_collection(collection_name=name)

    def list_collections(self) -> frozenset[str]:
        return frozenset(c.name for c in self._client.get_collections().collections)

    def upsert(self, collection: str, points: Sequence[StoredPoint]) -> None:
        models = self._models
        structs = []
        for point in points:
            vector: dict[str, Any] = {DENSE_VECTOR_NAME: list(point.dense)}
            if point.sparse is not None:
                vector[SPARSE_VECTOR_NAME] = models.SparseVector(
                    indices=list(point.sparse.indices), values=list(point.sparse.values)
                )
            structs.append(
                models.PointStruct(
                    id=_qdrant_id(point.id), vector=vector, payload=dict(point.payload)
                )
            )
        self._client.upsert(collection_name=collection, points=structs)

    def query(
        self,
        collection: str,
        dense: tuple[float, ...] | None,
        sparse: SparseVector | None,
        *,
        filter_logical: str | Sequence[str] | None = None,
        limit: int,
    ) -> list[ScoredPoint]:
        del sparse  # dense-only ranking in this adapter; see module docstring
        models = self._models
        query_filter = _build_filter(models, filter_logical)

        if dense is None:
            records, _ = self._client.scroll(
                collection_name=collection, scroll_filter=query_filter, limit=limit
            )
            return [ScoredPoint(id=str(r.id), score=0.0, payload=r.payload or {}) for r in records]

        results = self._client.query_points(
            collection_name=collection,
            query=list(dense),
            using=DENSE_VECTOR_NAME,
            query_filter=query_filter,
            limit=limit,
        ).points
        return [ScoredPoint(id=str(p.id), score=p.score, payload=p.payload or {}) for p in results]

    def delete_by_space(self, collection: str, space_id: str) -> int:
        models = self._models
        flt = models.Filter(
            must=[models.FieldCondition(key="space_id", match=models.MatchValue(value=space_id))]
        )
        count_before = self._client.count(collection_name=collection, count_filter=flt).count
        self._client.delete(
            collection_name=collection, points_selector=models.FilterSelector(filter=flt)
        )
        return int(count_before)


def _qdrant_id(local_id: str) -> str:
    """Qdrant point ids must be an unsigned int or a UUID; ours are arbitrary
    strings like ``"space-matter-alderman:a1"``. Map deterministically so the
    same ``StoredPoint.id`` always upserts to the same point."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, local_id))
