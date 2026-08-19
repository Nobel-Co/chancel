"""Reference ``VectorStore`` implementation: pure Python, stdlib + pydantic only.

Exists so the whole test suite -- and a forker reading this file -- can see
exactly what "vector search" means without a real vector database in the
loop. Dense scoring is cosine similarity; when a query carries a sparse
vector *and* a point carries one too, the score adds a sparse dot-product
term on top. Every operation is O(n) over the collection; this file
optimizes for readability, not throughput.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from chancel.stores.base import ScoredPoint, SparseVector, StoredPoint


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _sparse_dot(a: SparseVector, b: SparseVector) -> float:
    b_map = dict(zip(b.indices, b.values, strict=True))
    return sum(
        value * b_map.get(index, 0.0) for index, value in zip(a.indices, a.values, strict=True)
    )


def _matches_filter(
    payload: dict[str, str | None], filter_logical: str | Sequence[str] | None
) -> bool:
    if filter_logical is None:
        return True
    wanted = {filter_logical} if isinstance(filter_logical, str) else set(filter_logical)
    return payload.get("logical") in wanted


class InMemoryStore:
    """Pure-Python reference ``VectorStore``. No deps beyond stdlib + pydantic."""

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, StoredPoint]] = {}

    def create_collection(self, name: str, dense_dim: int, *, sparse: bool) -> None:
        del dense_dim, sparse  # unused by this reference impl; no schema to enforce
        self._collections[name] = {}

    def drop_collection(self, name: str) -> None:
        self._collections.pop(name, None)

    def list_collections(self) -> frozenset[str]:
        return frozenset(self._collections)

    def upsert(self, collection: str, points: Sequence[StoredPoint]) -> None:
        bucket = self._collections.setdefault(collection, {})
        for point in points:
            bucket[point.id] = point

    def query(
        self,
        collection: str,
        dense: tuple[float, ...] | None,
        sparse: SparseVector | None,
        *,
        filter_logical: str | Sequence[str] | None = None,
        limit: int,
    ) -> list[ScoredPoint]:
        candidates = [
            point
            for point in self._collections.get(collection, {}).values()
            if _matches_filter(point.payload, filter_logical)
        ]

        if dense is None:
            # No vector supplied: a filter-only "scroll", used by
            # verify_deletion. Score is meaningless here; report 0.0.
            return [ScoredPoint(id=p.id, score=0.0, payload=p.payload) for p in candidates[:limit]]

        scored = []
        for point in candidates:
            score = _cosine(dense, point.dense)
            if sparse is not None and point.sparse is not None:
                score += _sparse_dot(sparse, point.sparse)
            scored.append(ScoredPoint(id=point.id, score=score, payload=point.payload))
        scored.sort(key=lambda sp: sp.score, reverse=True)
        return scored[:limit]

    def delete_by_space(self, collection: str, space_id: str) -> int:
        bucket = self._collections.get(collection, {})
        doomed = [pid for pid, point in bucket.items() if point.payload.get("space_id") == space_id]
        for pid in doomed:
            del bucket[pid]
        return len(doomed)
