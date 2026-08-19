# FastEmbed Documentation

Fetched 2026-08-19 from official sources: GitHub (github.com/qdrant/fastembed), PyPI, and Qdrant documentation.

## Dense Text Embeddings

**Source:** https://github.com/qdrant/fastembed, https://qdrant.tech/documentation/fastembed/fastembed-quickstart/

### Basic Usage

```python
from fastembed import TextEmbedding

documents = [
    "This is built to be faster and lighter than other embedding libraries",
    "fastembed is supported by and maintained by Qdrant.",
]

embedding_model = TextEmbedding()
embeddings_list = list(embedding_model.embed(documents))
```

### TextEmbedding Class

The `TextEmbedding` class is the primary interface for dense text embeddings.

**Default Model:** `BAAI/bge-small-en-v1.5`  
**Default Dimension:** 384  

**Constructor:**
```python
TextEmbedding(
    model_name: str = "BAAI/bge-small-en-v1.5",
    cache_dir: str | None = None,
    threads: int | None = None,
    **kwargs
)
```

**Embed Method:**
```python
def embed(
    documents: str | Iterable[str],
    batch_size: int = 256,
    parallel: int | None = None,
    **kwargs
) -> Generator[np.ndarray, None, None]
```

The `.embed()` method returns a **generator** that yields `numpy.ndarray` objects. Each embedding is shape `(dimension,)` with `float32` dtype. Call `list(model.embed(documents))` to materialize all embeddings into memory.

### Supported Dense Models

**Source:** https://qdrant.github.io/fastembed/examples/Supported_Models/

The following are representative dense embedding models (full list available at the source):

| Model | Dimensions | Download Size |
|-------|-----------|---|
| BAAI/bge-small-en-v1.5 | 384 | 0.067 GB |
| BAAI/bge-small-zh-v1.5 | 512 | 0.090 GB |
| sentence-transformers/all-MiniLM-L6-v2 | 384 | 0.090 GB |
| snowflake/snowflake-arctic-embed-xs | 384 | 0.090 GB |
| jinaai/jina-embeddings-v2-small-en | 512 | 0.120 GB |
| BAAI/bge-base-en-v1.5 | 768 | 0.210 GB |
| intfloat/multilingual-e5-large | 1024 | 2.240 GB |

All models can be instantiated by passing the model name to the `TextEmbedding` constructor:

```python
model = TextEmbedding(model_name="BAAI/bge-base-en-v1.5")
embeddings = list(model.embed(documents))
```

---

## Sparse Text Embeddings (BM25)

**Source:** https://github.com/qdrant/fastembed (embedding.py, sparse/sparse_text_embedding.py)

### SparseTextEmbedding Class

The `SparseTextEmbedding` class provides sparse embeddings using BM25 and other sparse models.

**Constructor:**
```python
SparseTextEmbedding(
    model_name: str,
    cache_dir: str | None = None,
    **kwargs
)
```

**Embed Method:**
```python
def embed(
    documents: str | Iterable[str],
    batch_size: int = 256,
    parallel: int | None = None,
    **kwargs
) -> Iterable[SparseEmbedding]
```

The method returns an iterable yielding `SparseEmbedding` objects sequentially.

### BM25 Model

**Model name:** `Qdrant/bm25`  
**Download size:** 0.010 GB  

Example usage:

```python
from fastembed import SparseTextEmbedding

model = SparseTextEmbedding(model_name="Qdrant/bm25")
embeddings = list(model.embed(documents))
```

### SparseEmbedding Object

UNSOURCED: The exact structure of the `SparseEmbedding` class with `indices` and `values` attributes and their data types. Based on sparse embedding conventions, the object contains:

- **`indices`**: positions of non-zero values in the sparse vector
- **`values`**: corresponding numerical weights at those positions

The official implementation is imported from `fastembed.sparse.sparse_text_embedding`, but the detailed structure definition is not available in fetched documentation.

### Other Sparse Models

**Source:** https://qdrant.github.io/fastembed/examples/Supported_Models/

- `Qdrant/bm42-all-minilm-l6-v2-attentions` (0.090 GB, 30,522 vocab)
- `prithivida/Splade_PP_en_v1` (0.532 GB, 30,522 vocab)

---

## Model Caching and Download

**Source:** https://raw.githubusercontent.com/qdrant/fastembed/master/fastembed/common/model_management.py

### Cache Directory Configuration

Model weights are cached on disk for reuse after the first download. The cache location is controlled via the `cache_dir` parameter passed to `TextEmbedding()` or `SparseTextEmbedding()` constructors:

```python
model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5", cache_dir="/custom/cache/path")
```

UNSOURCED: The default cache directory location when `cache_dir=None` is not explicitly documented in fetched sources. Likely follows HuggingFace Hub defaults.

### Environment Variables

**`HF_HUB_OFFLINE`**: Controls offline mode

When set to `"1"`, `"TRUE"`, `"YES"`, or `"ON"`, FastEmbed operates in offline mode and accesses only cached models:

```bash
export HF_HUB_OFFLINE=1
```

### First-Use Download

**Source:** https://github.com/qdrant/fastembed (README)

When you instantiate a `TextEmbedding()` or `SparseTextEmbedding()` for the first time with a model:

1. FastEmbed downloads model weights automatically
2. Downloads are attempted from:
   - Local cache directory (if previously downloaded)
   - HuggingFace Hub
   - Google Cloud Storage
3. Model files are stored in compressed format (`.tar.gz`) and extracted to the cache directory
4. A `files_metadata.json` file tracks file sizes and blob IDs for verification

Subsequent calls reuse the cached model without re-downloading.

---

## Version and Python Support

**Source:** https://pypi.org/project/fastembed/

**Current Version:** 0.8.0 (Released 2026-03-23)

**Python Version Support:** >=3.10.0

Supported versions: Python 3.10, 3.11, 3.12, 3.13, 3.14

**Installation:**

```bash
pip install fastembed
```

For GPU acceleration:

```bash
pip install fastembed-gpu
```

---

## Unsourceable Items

The following details could not be sourced from official documentation:

1. **Default cache directory path**: The parameter-based configuration is documented, but the actual default location when `cache_dir=None` is not specified in fetched docs
2. **SparseEmbedding object structure**: The class definition with exact field names and data types for `indices` and `values` could not be extracted from available sources
3. **Environment variable for cache directory**: Only `HF_HUB_OFFLINE` was found; any `FASTEMBED_CACHE_DIR` or similar variable is not documented in fetched sources
