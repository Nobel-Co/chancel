"""chancel: provable scope isolation for AI retrieval."""

from chancel.exceptions import ChancelError, PromotionRefused, ScopeViolation
from chancel.model import (
    FIRM_COLLECTION,
    ActiveScope,
    DocumentId,
    RetrievalReceipt,
    RetrievedChunk,
    Scope,
    space_collection,
)
from chancel.policy import PolicyGate

__version__ = "0.1.0"

__all__ = [
    "FIRM_COLLECTION",
    "ActiveScope",
    "ChancelError",
    "DocumentId",
    "PolicyGate",
    "PromotionRefused",
    "RetrievalReceipt",
    "RetrievedChunk",
    "Scope",
    "ScopeViolation",
    "space_collection",
]
