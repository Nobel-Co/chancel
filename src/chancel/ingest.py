"""One ingestion path for every ``StorageMode`` -- apples-to-apples comparison.

Takes the dict shape produced by ``scripts/generate_corpus.py``'s
``generate()``: ``{"firm": [...], "matter-<id>": [...], ...}``, each doc a
dict with ``local_id``, ``scope``, ``space_id``, ``title``, ``text``.
"""

from __future__ import annotations

from chancel.embedders.base import Embedder
from chancel.model import DocumentId, Scope
from chancel.stores.base import StorageMode

CorpusDoc = dict[str, str | None]


def ingest_corpus(mode: StorageMode, corpus: dict[str, list[CorpusDoc]], embedder: Embedder) -> int:
    space_ids = [key for key in corpus if key != "firm"]
    all_docs = [doc for docs in corpus.values() for doc in docs]

    texts: list[str] = []
    for doc in all_docs:
        text = doc["text"]
        assert text is not None, "corpus doc missing required 'text' field"
        texts.append(text)

    dense_vectors = embedder.embed_dense(texts)
    sparse_vectors = embedder.embed_sparse(texts)
    sparse_supported = sparse_vectors is not None

    mode.provision(space_ids, embedder.dense_dim, sparse_supported)

    for i, doc in enumerate(all_docs):
        scope_raw = doc["scope"]
        local_id = doc["local_id"]
        title = doc["title"]
        assert scope_raw is not None, "corpus doc missing required 'scope' field"
        assert local_id is not None, "corpus doc missing required 'local_id' field"
        assert title is not None, "corpus doc missing required 'title' field"

        document_id = DocumentId(
            scope=Scope(scope_raw), space_id=doc["space_id"], local_id=local_id
        )
        sparse = sparse_vectors[i] if sparse_vectors is not None else None
        mode.ingest(document_id, title, texts[i], dense_vectors[i], sparse)

    return len(all_docs)
