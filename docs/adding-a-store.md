# Adding a store

A "store" is a `VectorStore`: the low-level, collection-addressed backend that physically holds
points. It knows **nothing** about firm/space semantics — that is `StorageMode`'s job, one layer
up. So adding a backend (pgvector, Weaviate, …) is implementing the collection-addressed contract
and letting the existing `isolated` / `filtered` / `shared` layouts sit on top of it unchanged.

Read `chancel/stores/inmemory.py` as you go: it is the reference implementation, dependency-free,
and it is the readable contract in executable form. Anything ambiguous in the protocol below is
answered there.

## The contract

`VectorStore` (in `chancel/stores/base.py`) is six methods:

```python
class VectorStore(Protocol):
    def create_collection(self, name: str, dense_dim: int, *, sparse: bool) -> None: ...
    def drop_collection(self, name: str) -> None: ...
    def list_collections(self) -> frozenset[str]: ...
    def upsert(self, collection: str, points: Sequence[StoredPoint]) -> None: ...
    def query(
        self,
        collection: str,
        dense: tuple[float, ...] | None,
        sparse: SparseVector | None,
        *,
        filter_logical: str | Sequence[str] | None = None,
        limit: int,
    ) -> list[ScoredPoint]: ...
    def delete_by_space(self, collection: str, space_id: str) -> int: ...
```

The three details that trip people up, all resolved in `inmemory.py`:

- **`drop_collection` on a missing collection is not an error.** `isolated`'s deletion path relies
  on this.
- **`list_collections()` is the independent deletion check.** It must reflect reality without
  running a query — it is what lets `isolated` certify a matter is gone *without trusting the
  query path under test*. Do not implement it by querying.
- **`query(dense=None, ...)` is a filter-only scroll** — no ranking, score reported as `0.0`.
  `verify_deletion` uses it to check for the *presence* of points, not to rank them. And
  `filter_logical` matches the payload's `"logical"` field: a single value, a sequence (match-any
  / OR), or `None` for no filter. The `isolated` layout only ever passes `None`, because the
  collection *is* the boundary.

## Register it (optional)

Add a branch to `build_store()` in `chancel/registry.py`, deferred-imported so an optional client
library never loads unless requested:

```python
    if kind == "pgvector":
        from chancel.stores.pgvector import PgVectorStore

        return PgVectorStore(location)
```

## Prove it

```bash
uv run pytest tests/conformance
```

`tests/conformance/test_store_conformance.py` exercises every registered store against the same
`VectorStore` behavioral contract, and the storage-layout tests then run the `isolated` /
`filtered` / `shared` modes on top of it. A conforming store passes with no suite edits — and
because the three modes are written entirely against this protocol, a correct backend inherits all
three layouts, including the defended `isolated` one, for free.
