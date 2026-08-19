"""Domain model for scope isolation.

Invariant: a DocumentId cannot express an inconsistent scope; an ActiveScope
is the only source of retrieval authority.
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

# Space ids must not collide with the firm collection name and must not carry
# characters that could smuggle a separator into a collection name (e.g. "/",
# "..", or another "-space-" segment). This is the only pattern space ids are
# validated against, everywhere a space_id enters the system.
SPACE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def _validate_space_id(space_id: str) -> str:
    if space_id == "firm" or not SPACE_ID_PATTERN.match(space_id):
        raise ValueError(f"invalid space_id: {space_id!r}")
    return space_id


class Scope(StrEnum):
    """FIRM crosses every space; SPACE never leaves its space."""

    FIRM = "firm"
    SPACE = "space"


FIRM_COLLECTION = "firm"


def space_collection(space_id: str) -> str:
    """Collection name for a space. Validates space_id first."""
    _validate_space_id(space_id)
    return f"space-{space_id}"


class DocumentId(BaseModel, frozen=True):
    """Identifies a document and the scope it lives in.

    The scope and space_id fields are cross-validated in both directions so
    no instance can claim FIRM scope with a space_id, or SPACE scope without
    a valid one.
    """

    scope: Scope
    space_id: str | None = None
    local_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_scope_consistency(self) -> Self:
        if self.scope is Scope.FIRM and self.space_id is not None:
            raise ValueError("firm-scoped DocumentId must not carry a space_id")
        if self.scope is Scope.SPACE:
            if self.space_id is None:
                raise ValueError("space-scoped DocumentId requires a space_id")
            _validate_space_id(self.space_id)
        return self

    @property
    def collection(self) -> str:
        if self.scope is Scope.FIRM:
            return FIRM_COLLECTION
        assert self.space_id is not None  # enforced by validator
        return space_collection(self.space_id)


class ActiveScope(BaseModel, frozen=True):
    """Constructed once per query. The only source of retrieval authority."""

    space_id: str

    @field_validator("space_id")
    @classmethod
    def _validate(cls, value: str) -> str:
        return _validate_space_id(value)

    @property
    def allowed_collections(self) -> frozenset[str]:
        return frozenset({FIRM_COLLECTION, space_collection(self.space_id)})


class RetrievedChunk(BaseModel, frozen=True):
    doc_id: DocumentId
    text: str
    score: float


class RetrievalReceipt(BaseModel, frozen=True):
    """Audit record of one authorize() decision. Never carries query content."""

    ts: str
    space_id: str
    decision: Literal["allow", "deny"]
    requested_collections: tuple[str, ...]
    allowed_collections: tuple[str, ...]
    reason: str
    # sha256 hex digest of the query text, supplied by the caller. Receipts
    # must never carry the query itself.
    query_fingerprint: str
    returned_doc_ids: tuple[str, ...]
    # Filled in by the audit module's hash chain. None until chained.
    prev_sha256: str | None = None

    def canonical_json(self) -> str:
        """Deterministic JSON serialization of all fields, sorted keys, no
        whitespace variance. The audit module computes
        line_hash = sha256(canonical_json()) to build its hash chain.
        """
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
