"""The single caller of ``StorageMode.search`` in this codebase.

Consumes the gate invariant from ``chancel.policy``: it always requests the
active scope's own structural allowlist via ``PolicyGate.default_allowlist``,
then narrows it through ``PolicyGate.authorize()``. No public signature in
this module accepts a collection name or a filter -- a leak test asserts
this via introspection of ``Retriever.retrieve``. A CI grep separately
enforces that no other module in the codebase calls ``StorageMode.search``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from chancel.embedders.base import Embedder
from chancel.exceptions import ScopeViolation
from chancel.model import ActiveScope, RetrievalReceipt, RetrievedChunk
from chancel.policy import PolicyGate
from chancel.stores.base import StorageMode


class Retriever:
    def __init__(
        self,
        gate: PolicyGate,
        mode: StorageMode,
        embedder: Embedder,
        audit: Callable[[RetrievalReceipt], None] | None = None,
    ) -> None:
        self._gate = gate
        self._mode = mode
        self._embedder = embedder
        self._audit = audit

    def retrieve(self, scope: ActiveScope, query: str, *, limit: int = 6) -> list[RetrievedChunk]:
        try:
            requested = self._gate.default_allowlist(scope)
            authorized = self._gate.authorize(scope, requested)
        except ScopeViolation as exc:
            self._write_receipt(
                scope,
                decision="deny",
                reason=exc.reason,
                requested=exc.requested,
                allowed=(),
                query=query,
                returned=(),
            )
            raise

        dense_vectors = self._embedder.embed_dense([query])
        sparse_vectors = self._embedder.embed_sparse([query])
        dense = dense_vectors[0]
        sparse = sparse_vectors[0] if sparse_vectors is not None else None

        chunks = self._mode.search(authorized, dense, sparse, limit)

        self._write_receipt(
            scope,
            decision="allow",
            reason="authorized",
            requested=tuple(sorted(requested)),
            allowed=tuple(sorted(authorized)),
            query=query,
            returned=tuple(chunk.doc_id.local_id for chunk in chunks),
        )
        return chunks

    def _write_receipt(
        self,
        scope: ActiveScope,
        *,
        decision: Literal["allow", "deny"],
        reason: str,
        requested: tuple[str, ...],
        allowed: tuple[str, ...],
        query: str,
        returned: tuple[str, ...],
    ) -> None:
        if self._audit is None:
            return
        receipt = RetrievalReceipt(
            ts=datetime.now(UTC).isoformat(),
            space_id=scope.space_id,
            decision=decision,
            requested_collections=requested,
            allowed_collections=allowed,
            reason=reason,
            query_fingerprint=hashlib.sha256(query.encode()).hexdigest(),
            returned_doc_ids=returned,
        )
        self._audit(receipt)
