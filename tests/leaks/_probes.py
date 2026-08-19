"""Shared helpers for the leak suite.

Kept test-only (this file is not importable from ``chancel``); the *evaluation*
logic that the demo and the tests must agree on lives in ``chancel.demo`` and
is imported from there. What lives here is scaffolding: building a full
Retriever+gate stack over an ``InMemoryStore``, extracting canary strings from
the generated corpus, and the manual BM25/IDF reproduction that finding 2
needs (no fastembed required).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from generate_corpus import generate, write_corpus

from chancel.embedders.hash_stub import HashStubEmbedder
from chancel.ingest import ingest_corpus
from chancel.model import ActiveScope, RetrievalReceipt
from chancel.policy import PolicyGate
from chancel.registry import build_mode
from chancel.retriever import Retriever
from chancel.stores.base import StorageMode, VectorStore
from chancel.stores.inmemory import InMemoryStore

SCOPE_SPACE = "matter-alderman"
TARGET_SPACE = "matter-brightwater"
SPACE_IDS = (SCOPE_SPACE, TARGET_SPACE)

_CANARY_RE = re.compile(r"CANARY-[A-Z]+-[0-9a-f]{12}")


class RecordingAudit:
    """Captures every receipt the retriever writes."""

    def __init__(self) -> None:
        self.receipts: list[RetrievalReceipt] = []

    def __call__(self, receipt: RetrievalReceipt) -> None:
        self.receipts.append(receipt)


@dataclass(frozen=True)
class Stack:
    backend: str
    store: VectorStore
    mode: StorageMode
    gate: PolicyGate
    embedder: HashStubEmbedder
    retriever: Retriever
    audit: RecordingAudit
    corpus: dict[str, list[dict[str, str | None]]]


def build_stack(backend: str, *, seed: int = 1789, sparse: bool = True) -> Stack:
    """A full ``InMemoryStore`` stack for ``backend`` with the corpus ingested."""
    store = InMemoryStore()
    mode = build_mode(backend, store)
    embedder = HashStubEmbedder()
    corpus = generate(seed)
    ingest_corpus(mode, corpus, embedder)
    gate = PolicyGate(SPACE_IDS)
    audit = RecordingAudit()
    retriever = Retriever(gate, mode, embedder, audit=audit)
    return Stack(
        backend=backend,
        store=store,
        mode=mode,
        gate=gate,
        embedder=embedder,
        retriever=retriever,
        audit=audit,
        corpus=corpus,
    )


def canary_for(corpus: dict[str, list[dict[str, str | None]]], matter: str) -> str:
    """The distinctive canary string embedded in ``matter``'s documents."""
    for doc in corpus[matter]:
        text = doc["text"] or ""
        found = _CANARY_RE.search(text)
        if found:
            return found.group(0)
    raise AssertionError(f"no canary found in {matter}")


def local_ids_for(corpus: dict[str, list[dict[str, str | None]]], matter: str) -> frozenset[str]:
    return frozenset(str(doc["local_id"]) for doc in corpus.get(matter, []))


def text_contains_canary(chunks_text: Sequence[str], canary: str) -> bool:
    return any(canary in text for text in chunks_text)


# --------------------------------------------------------------------------
# Manual BM25 / IDF -- the offline reproduction of finding 2.
#
# Uses the real ``HashStubEmbedder`` sparse vectors as term-frequency maps, so
# the tokenization is the same one the store would see. IDF is computed over an
# explicit *population* of documents: that population is the knob that models
# "shard-wide (filtered) vs per-tenant (isolated)" statistics.
# --------------------------------------------------------------------------

_EMBEDDER = HashStubEmbedder()


def term_frequencies(text: str) -> dict[int, float]:
    """{term-index: count} for one document, via the hash_stub sparse vector."""
    sparse = _EMBEDDER.embed_sparse([text])
    assert sparse is not None  # hash_stub always supports sparse
    vector = sparse[0]
    return dict(zip(vector.indices, vector.values, strict=True))


def bm25_score(
    query_tf: dict[int, float],
    doc_tf: dict[int, float],
    population: Sequence[dict[int, float]],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """Textbook BM25 score of one document for one query.

    ``population`` is the IDF corpus: the set of documents whose statistics
    (total count N, per-term document frequency df, average length avgdl) the
    IDF is computed over. Passing a shard-wide population reproduces filtered
    mode; passing the tenant's own documents reproduces isolated mode.
    """
    n_docs = len(population)
    if n_docs == 0:
        return 0.0
    avgdl = sum(sum(tf.values()) for tf in population) / n_docs
    doclen = sum(doc_tf.values())
    score = 0.0
    for term in query_tf:
        df = sum(1 for tf in population if term in tf)
        if df == 0:
            continue
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
        freq = doc_tf.get(term, 0.0)
        denom = freq + k1 * (1.0 - b + b * doclen / avgdl)
        score += idf * (freq * (k1 + 1.0)) / denom
    return score


def padded_matter_docs(
    tmp_path: Path, matter: str, pad_count: int, *, seed: int = 1789
) -> list[dict[str, str | None]]:
    """``matter``'s documents after ``write_corpus`` pads it with ``pad_count``
    filler docs -- exercised through the real generator so the padding
    vocabulary skew is the generator's, not a copy of it."""
    out = tmp_path / f"pad-{matter}-{pad_count}"
    write_corpus(out, seed, matter, pad_count)
    lines = (out / f"{matter}.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines if line]


def adversarial_scope() -> ActiveScope:
    return ActiveScope(space_id=SCOPE_SPACE)
