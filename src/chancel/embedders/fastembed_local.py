"""Local, no-API-key ``Embedder`` backed by fastembed.

Optional dependency: ``pip install chancel[local]``. Dense embedding uses
``BAAI/bge-small-en-v1.5`` (dimension 384, the fastembed default); sparse
embedding uses the BM25 model ``Qdrant/bm25``, converting fastembed's
``SparseEmbedding`` (``indices`` / ``values`` arrays) into chancel's
``SparseVector``.

**First use downloads model weights** (a few hundred MB combined) from the
fastembed/HuggingFace Hub cache the first time either model is instantiated;
subsequent runs reuse the on-disk cache and need no network. This is why the
unit test tier uses ``HashStubEmbedder`` instead -- this adapter is
exercised only where a download is acceptable (conformance/integration,
``importorskip("fastembed")``-guarded).
"""

from __future__ import annotations

from collections.abc import Sequence

from chancel.stores.base import SparseVector

DENSE_MODEL = "BAAI/bge-small-en-v1.5"
DENSE_DIM = 384
SPARSE_MODEL = "Qdrant/bm25"


class FastEmbedLocalEmbedder:
    """Local dense + sparse ``Embedder`` via fastembed. See module docstring
    for the first-use download."""

    dense_dim: int = DENSE_DIM

    def __init__(self, dense_model: str = DENSE_MODEL, sparse_model: str = SPARSE_MODEL) -> None:
        try:
            from fastembed import SparseTextEmbedding, TextEmbedding
        except ImportError as exc:
            raise ImportError(
                "the fastembed_local embedder requires the 'fastembed' package; "
                "install it with `pip install chancel[local]`"
            ) from exc

        self._dense_model = TextEmbedding(model_name=dense_model)
        self._sparse_model = SparseTextEmbedding(model_name=sparse_model)

    def embed_dense(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        return [tuple(float(x) for x in vector) for vector in self._dense_model.embed(list(texts))]

    def embed_sparse(self, texts: Sequence[str]) -> list[SparseVector] | None:
        vectors: list[SparseVector] = []
        for sparse in self._sparse_model.embed(list(texts)):
            indices = tuple(int(i) for i in sparse.indices)
            values = tuple(float(v) for v in sparse.values)
            vectors.append(SparseVector(indices=indices, values=values))
        return vectors
