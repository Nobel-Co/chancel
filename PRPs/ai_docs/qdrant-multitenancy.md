# Qdrant Multitenancy & Sparse Vector IDF Documentation

**Fetched:** 2026-08-19

## 1. Vendor Recommendation: Single Collection vs Multiple Collections

> Creating a separate collection for each tenant is rarely the most efficient approach. Each collection carries its own resource overhead, so creating many collections can quickly become expensive.

**Source:** https://qdrant.tech/documentation/manage-data/multitenancy/

---

## 2. Exceptions: When Multiple Collections ARE Warranted

> Only create multiple collections when you have a limited number of tenants that need strict isolation.

**Source:** https://qdrant.tech/documentation/manage-data/multitenancy/

The vendor identifies **strict isolation** and **compliance requirements** as the primary justification for dedicated collections, noting that shards require significant resources and should be reserved for scenarios where the isolation benefit outweighs the operational cost.

---

## 3. Collection Count Ceiling & Practical Limits

> Qdrant Cloud limits each cluster to a maximum of 1000 collections by default.

**Source:** https://qdrant.tech/documentation/manage-data/multitenancy/

**Recommended Approaches (within a single collection):**

The vendor endorses three strategies for tenant isolation without multiple collections:

1. **Partition by payload** – Efficient for numerous small, similarly-sized tenants
2. **User-defined sharding** – Dedicated shard per tenant; suited for fewer, larger tenants
3. **Tiered multitenancy** – Hybrid approach combining payload partitioning with dedicated shards for growth

---

## 4. Sparse Vector IDF Computation under Payload-Based Partitioning

**UNSOURCED:** IDF (Inverse Document Frequency) computation details under payload-based multitenancy

The Qdrant documentation references BM25 sparse vectors and full-text search capabilities but the detailed technical documentation on how IDF statistics are computed (shard-wide vs per-tenant vs collection-wide) could not be accessed via available documentation URLs.

**What was confirmed to exist but not fully accessible:**
- BM25 implementation available via server-side inference (model identifier: `qdrant/bm25`)
- Sparse vectors represent documents with term weights
- References to "idf search parameter" and IDF modifiers exist but detailed specifications were not retrievable

**Attempted documentation URLs (returned 404 or inaccessible):**
- https://qdrant.tech/documentation/inference/inference-bm25/
- https://qdrant.tech/documentation/search/full-text-search/
- https://qdrant.tech/documentation/tutorials/text-search/

---

## 5. Keyword Payload Index Creation & Tenant Key Marking

### Creating a Keyword Index

**REST API:**
```json
PUT /collections/{collection_name}/index
{
    "field_name": "name_of_the_field_to_index",
    "field_schema": "keyword"
}
```

**Python SDK:**
```python
client.create_payload_index(
    collection_name="{collection_name}",
    field_name="name_of_the_field_to_index",
    field_schema=models.PayloadSchemaType.KEYWORD,
)
```

**Source:** https://qdrant.tech/documentation/manage-data/indexing/

### Marking a Field as Tenant Key with `is_tenant`

The `is_tenant` parameter marks payload fields used for tenant identification. This optimization "will tell Qdrant which fields are used for tenant identification" and optimizes storage layout for faster tenant-specific searches by localizing tenant data on disk.

**Available since:** v1.11.0

**Supported types:** `keyword` and `uuid` only

**REST API:**
```json
PUT /collections/{collection_name}/index
{
    "field_name": "payload_field_name",
    "field_schema": {
        "type": "keyword",
        "is_tenant": true
    }
}
```

**Python SDK:**
```python
client.create_payload_index(
    collection_name="{collection_name}",
    field_name="payload_field_name",
    field_schema=models.KeywordIndexParams(
        type=models.KeywordIndexType.KEYWORD,
        is_tenant=True,
    ),
)
```

**Source:** https://qdrant.tech/documentation/manage-data/indexing/

---

## Summary

**Successfully sourced (with verbatim quotes):**
- ✓ Multitenancy recommendation (single collection + payload vs multiple)
- ✓ Exception criteria (strict isolation, compliance)
- ✓ Collection count limit (1000 per cluster)
- ✓ Keyword payload index API syntax (REST & Python)
- ✓ `is_tenant` parameter syntax and behavior (v1.11.0+)

**Could not source:**
- ✗ IDF computation methodology under payload-based partitioning (shard-wide vs per-tenant behavior)
- ✗ `idf` search parameter / IDF modifier documentation
- ✗ miniCOIL or BM25 inverse document frequency specifics
- Note: Documentation references exist but detailed content was not accessible via WebFetch

---

## Sparse-vector IDF under payload-based partitioning (RESOLVED — was UNSOURCED above)

Escalation note: the section below was sourced 2026-08-19 by the orchestrator after the
first-pass agent could not reach it. Source: https://qdrant.tech/documentation/manage-data/multitenancy/
(the multitenancy page itself, "Limitations" and "Per-tenant IDF statistics" sections).
Quotes are verbatim. THIS IS THE LOAD-BEARING CITATION FOR LEAK FINDING 2.

From the Limitations section:

> When using sparse vector search with the IDF modifier, payload-based partitioning alone
> doesn't isolate IDF statistics. By default, all tenants share the same shard-wide term
> frequencies. Use the `idf` search parameter to scope statistics to a single tenant.

From the Per-tenant IDF statistics section:

> BM25 and miniCOIL sparse vector searches use the inverse document frequency (IDF) to score
> matching documents, giving rarer terms more weight than common ones. Calculating the IDF
> requires two statistics: the total number of documents and the number of documents
> containing each term.
>
> By default, these statistics are computed across the entire shard being queried. When using
> payload-filter-based multitenancy, this blends every tenant's vocabulary into one set of
> statistics, so a term's IDF no longer reflects its rarity within a specific tenant's data.
>
> The `idf` search parameter lets you correct this by narrowing the population — the IDF
> corpus — that Qdrant computes statistics over. It accepts a payload filter that scopes
> the data.

Code example shape (per-tenant IDF scoping):

```json
"params": {"idf": {"corpus": {"must": [{"key": "tenant", "match": {"value": "acme"}}]}}}
```

Implication for chancel: under `filtered` mode the returned points are isolated but the
ranking statistics are not — one tenant's corpus measurably shifts another tenant's scores
unless every caller remembers the `idf` parameter on every query. Under `isolated` mode the
statistics cannot cross because the collections do not share a shard. The existence of the
`idf` escape hatch is itself the finding: the filter model requires per-query vigilance where
the collection model requires none.

Also from this page, the single-collection recommendation verbatim:

> Creating a separate collection for each tenant is rarely the most efficient approach. Each
> collection carries its own resource overhead, so creating many collections can quickly
> become expensive. Only create multiple collections when you have a limited number of
> tenants that need strict isolation.

That last sentence is the exception chancel occupies: a law firm's matters are "a limited
number of tenants that need strict isolation."
