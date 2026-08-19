# Qdrant Python Client API Reference

**Fetched:** 2026-08-19  
**Version:** 1.19.0 (current as of August 4, 2026)  
**Sources:**
- https://github.com/qdrant/qdrant-client (README)
- https://qdrant.tech/documentation/concepts/collections/
- https://qdrant.tech/documentation/concepts/filtering/
- https://qdrant.tech/documentation/concepts/vectors/
- https://pypi.org/project/qdrant-client/
- https://qdrant.tech/documentation/manage-data/payload/
- https://qdrant.tech/documentation/manage-data/points/
- https://qdrant.tech/documentation/inference/inference-bm25/

---

## 1. Local Mode WITHOUT a Server

### In-Memory Mode
Local mode is useful for development, prototyping, and testing. QdrantClient can run without a separate server instance.

```python
from qdrant_client import QdrantClient

client = QdrantClient(":memory:")
```

### Persistent On-Disk Mode
```python
client = QdrantClient(path="path/to/db")
```

**Use Cases:** Development, prototyping, testing, CI/CD pipelines, notebook environments, prototyping before scaling to server mode. Local mode allows developers to "run same code in local mode without running Qdrant server."

**Documented Limitations:** None explicitly stated in fetched docs. To scale to production, switch to URL-based connection: `client = QdrantClient(url="http://localhost:6333")`

---

## 2. Collection Lifecycle

### Create Collection
```python
client.create_collection(
    collection_name="{collection_name}",
    vectors_config=models.VectorParams(size=100, distance=models.Distance.COSINE),
)
```

**VectorParams Parameters:**
- `size`: vector dimensionality (integer)
- `distance`: `models.Distance.COSINE`, `models.Distance.EUCLID`, `models.Distance.DOT`, or `models.Distance.MANHATTAN`

### Multiple Named Vectors
```python
client.create_collection(
    collection_name="{collection_name}",
    vectors_config={
        "image": models.VectorParams(size=4, distance=models.Distance.DOT),
        "text": models.VectorParams(size=8, distance=models.Distance.COSINE),
    },
)
```

### Delete Collection
```python
client.delete_collection(collection_name="{collection_name}")
```

### Get All Collections
```python
client.get_collections()
```

### Check Collection Existence
```python
client.collection_exists(collection_name="{collection_name}")
```

---

## 3. Creating a Keyword Payload Index

### Basic Syntax
```python
client.create_payload_index(
    collection_name="{collection_name}",
    field_name="name_of_the_field_to_index",
    field_schema=models.PayloadSchemaType.KEYWORD,
)
```

**Parameters:**
- `collection_name`: target collection identifier (string)
- `field_name`: payload field to be indexed (string)
- `field_schema`: data type, e.g., `models.PayloadSchemaType.KEYWORD`

**Note from docs:** "Indexed fields also affect the vector index." Recommended to index fields that "could potentially constrain the results the most."

**Tenant-Key Variant:** UNSOURCED — not found in official documentation accessed.

---

## 4. Filtered Search

### Basic Filter with must Clause
```python
from qdrant_client import QdrantClient, models

client.scroll(
    collection_name="{collection_name}",
    scroll_filter=models.Filter(
        must=[
            models.FieldCondition(
                key="city",
                match=models.MatchValue(value="London"),
            ),
            models.FieldCondition(
                key="color",
                match=models.MatchValue(value="red"),
            ),
        ]
    ),
)
```

### Filter with should Clause (OR Logic)
```python
scroll_filter=models.Filter(
    should=[
        models.FieldCondition(key="city", match=models.MatchValue(value="London")),
        models.FieldCondition(key="color", match=models.MatchValue(value="red")),
    ]
)
```

### Combined must and must_not
```python
scroll_filter=models.Filter(
    must=[
        models.FieldCondition(key="city", match=models.MatchValue(value="London")),
    ],
    must_not=[
        models.FieldCondition(key="color", match=models.MatchValue(value="red")),
    ],
)
```

### Classes and Models
- `models.Filter`: container for filter clauses
- `models.FieldCondition`: condition on a payload field
- `models.MatchValue`: matches a specific value

### Passing to query_points/search
Both `query_points` and `scroll` accept a `query_filter` parameter (or `scroll_filter` for scroll):

```python
client.query_points(
    collection_name="{collection_name}",
    query_filter=models.Filter(must=[...]),
)
```

---

## 5. Sparse Vector Configuration

### Collection Creation with Sparse Vectors
```python
client.create_collection(
    collection_name="{collection_name}",
    vectors_config={},
    sparse_vectors_config={
        "text": models.SparseVectorParams(),
    },
)
```

**Models:**
- `models.SparseVectorParams`: configuration for named sparse vector (no required parameters)
- Sparse vectors dynamically allocate during insertion and lack fixed length
- Non-zero values currently limited to u32 datatype range (4,294,967,295)

### Sparse Vector Structure
Sparse vectors are defined by non-zero elements and their indexes:
```json
{
    "indexes": [1, 3, 5, 7],
    "values": [0.1, 0.2, 0.3, 0.4]
}
```

### Upserting with Named Sparse Vectors
```python
client.upsert(
    collection_name="{collection_name}",
    points=[
        models.PointStruct(
            id=1,
            vector={
                "text": models.SparseVector(
                    indices=[1, 3, 5, 7],
                    values=[0.1, 0.2, 0.3, 0.4]
                )
            },
        )
    ],
)
```

### Querying with Sparse Vectors
```python
result = client.query_points(
    collection_name="{collection_name}",
    query=models.SparseVector(
        indices=[1, 3, 5, 7], 
        values=[0.1, 0.2, 0.3, 0.4]
    ),
    using="text",
).points
```

**Parameters:**
- `query`: `models.SparseVector` with indices and values
- `using`: name of the sparse vector field to query

### IDF Modifier
UNSOURCED: `models.Modifier.IDF` — not found in official documentation accessed. BM25 configuration exists via `models.Document(text="...", model="Qdrant/bm25")` but explicit Modifier.IDF class not documented.

---

## 6. Upsert Operations

### PointStruct with Named Vectors and Payload
```python
models.PointStruct(
    id=1,
    vector={
        "image": [0.9, 0.1, 0.1, 0.2],
        "text": [0.4, 0.7, 0.1, 0.8, 0.1, 0.1, 0.9, 0.2],
    },
    payload={
        "color": "red",
    }
)
```

### Upsert Method
```python
client.upsert(
    collection_name="{collection_name}",
    points=[
        models.PointStruct(id=..., vector=..., payload=...),
        # ... more points
    ],
)
```

**PointStruct Parameters:**
- `id`: unique point identifier (integer)
- `vector`: dict mapping named vector names to float arrays, or single array for single vector
- `payload`: dict of metadata fields and values

**Named Vector Form:**
The `vector` parameter accepts a dictionary for multiple named vectors per point:
```python
vector={
    "vector_name_1": [0.1, 0.2, 0.3, ...],
    "vector_name_2": [0.9, 0.8, 0.7, ...],
}
```

---

## Implementation Notes

1. **Local mode syntax** (`":memory:"` and `path="..."`) is confirmed for development/testing.
2. **Collection methods** follow naming convention: `create_collection()`, `delete_collection()`, `get_collections()`, `collection_exists()`.
3. **Payload indexing** uses `PayloadSchemaType` enum for field schema types.
4. **Filter syntax** chains `models.Filter()` with `models.FieldCondition()` and `models.MatchValue()`.
5. **Sparse vectors** require explicit `SparseVectorParams()` in collection creation and `SparseVector()` objects with indices/values for upsert/query.
6. **PointStruct** unifies id, named vectors (as dict), and payload in one object for upsert.

---

## Version Information

**qdrant-client: 1.19.0** — Released August 4, 2026  
Installable via: `pip install qdrant-client`

---

## Unsourced Claims

- **`models.Modifier.IDF` for sparse vectors** — Not found in official Qdrant docs fetched. BM25 sparse embedding exists but explicit IDF modifier class/syntax not confirmed.
- **Local mode limitations** — No explicit limitations documented in fetched sources; scaling to server mode is the stated pattern.
- **Tenant-key variant of `create_payload_index`** — Not found in official docs accessed.
