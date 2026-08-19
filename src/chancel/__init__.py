"""chancel: provable scope isolation for AI retrieval."""

from chancel.embedders.hash_stub import HashStubEmbedder
from chancel.exceptions import ChancelError, PromotionRefused, ScopeViolation
from chancel.ingest import ingest_corpus
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
from chancel.registry import build_mode, build_store
from chancel.retriever import Retriever
from chancel.stores.filtered import FilteredStore
from chancel.stores.inmemory import InMemoryStore
from chancel.stores.isolated import IsolatedStore
from chancel.stores.shared import SharedStore

__version__ = "0.1.0"

__all__ = [
    "FIRM_COLLECTION",
    "ActiveScope",
    "ChancelError",
    "DocumentId",
    "FilteredStore",
    "HashStubEmbedder",
    "InMemoryStore",
    "IsolatedStore",
    "PolicyGate",
    "PromotionRefused",
    "RetrievalReceipt",
    "RetrievedChunk",
    "Retriever",
    "Scope",
    "ScopeViolation",
    "SharedStore",
    "build_mode",
    "build_store",
    "ingest_corpus",
    "space_collection",
]
