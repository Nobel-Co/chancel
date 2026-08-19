"""Finding 3 -- the cross-space read is unrepresentable under isolated, and
freely representable under filtered.

isolated: there is no public API that expresses "retrieve from another space's
collection." The retriever's signature admits only {scope, query, limit}; the
StorageMode.search boundary takes an ``authorized`` set that only the gate
produces; and asking the gate to authorize a foreign collection RAISES. The
attack cannot be constructed.

filtered: the SAME low-level freedom the isolated layout removed is
reintroduced at the translation site (stores/filtered.py search()). Because the
physical collection is shared and the boundary is a filter argument, a
brightwater context can call ``store.query(collection="corpus",
filter_logical="space-matter-alderman")`` directly and get the other space's
data back. The call is representable and returns foreign rows -- RED.
"""

from __future__ import annotations

import inspect

import pytest
from _probes import SCOPE_SPACE, SPACE_IDS, TARGET_SPACE, build_stack, local_ids_for

from chancel.exceptions import ScopeViolation
from chancel.model import ActiveScope, space_collection
from chancel.retriever import Retriever
from chancel.stores.filtered import CORPUS_COLLECTION
from chancel.stores.isolated import IsolatedStore


def test_retriever_signature_has_no_collection_or_filter_channel() -> None:
    """The only public retrieval entry point exposes exactly {scope, query, limit}.

    No ``collection``, no ``filter``, no ``space`` parameter exists to smuggle a
    foreign target through -- the unrepresentability is a fact about the
    signature, asserted by introspection.
    """
    sig = inspect.signature(Retriever.retrieve)
    params = [p for p in sig.parameters if p != "self"]
    assert params == ["scope", "query", "limit"], (
        f"Retriever.retrieve exposes {params}; a new parameter here (a collection, "
        "a filter, a space override) would open a channel finding 3 says must not exist."
    )
    # `authorized` -- the only thing that names collections at the search
    # boundary -- is produced by the gate, never accepted from a caller.
    search_sig = inspect.signature(IsolatedStore.search)
    assert "authorized" in search_sig.parameters
    assert "collection" not in search_sig.parameters
    assert "filter_logical" not in search_sig.parameters


def test_isolated_gate_refuses_to_authorize_a_foreign_collection() -> None:
    """Asking the authority layer for another space's collection RAISES.

    This is the cross-space read expressed at the one place it *could* be
    expressed -- the gate -- and the gate denies it (bounded by
    scope.allowed_collections, not merely by the known-spaces registry).
    """
    stack = build_stack("isolated")
    scope = ActiveScope(space_id=SCOPE_SPACE)
    foreign = space_collection(TARGET_SPACE)

    with pytest.raises(ScopeViolation) as excinfo:
        stack.gate.authorize(scope, (foreign,))
    assert foreign in excinfo.value.offending
    assert excinfo.value.reason == "requested collection outside active scope"


def test_isolated_search_only_touches_authorized_collections() -> None:
    """Even handed the store directly, isolated search reaches only what the gate
    authorized -- there is no collection argument for a foreign name to enter."""
    stack = build_stack("isolated")
    scope = ActiveScope(space_id=SCOPE_SPACE)
    authorized = stack.gate.authorize(scope, stack.gate.default_allowlist(scope))
    # The authorized set structurally cannot contain the foreign collection.
    assert space_collection(TARGET_SPACE) not in authorized
    chunks = stack.mode.search(
        authorized, stack.embedder.embed_dense(["salvage seaworthiness"])[0], None, 20
    )
    foreign_ids = local_ids_for(stack.corpus, TARGET_SPACE)
    assert not ({c.doc_id.local_id for c in chunks} & foreign_ids)


def test_filtered_cross_space_call_is_representable_and_returns_foreign_data() -> None:
    """RED: from a brightwater context, one direct store call returns alderman data.

    This is the exact freedom stores/filtered.py's search() translation site
    reintroduces on purpose: the physical collection is shared, so the
    ``filter_logical`` argument is just a string a caller can set to any space.
    """
    stack = build_stack("filtered")
    foreign_logical = space_collection(SCOPE_SPACE)  # alderman, from a "brightwater" caller

    # Construct EXACTLY the call the isolated layout makes unrepresentable.
    rows = stack.store.query(
        CORPUS_COLLECTION,
        None,
        None,
        filter_logical=foreign_logical,
        limit=100,
    )
    foreign_rows = [r for r in rows if r.payload.get("space_id") == SCOPE_SPACE]
    assert foreign_rows, (
        "EXPECTED-RED REGRESSION: the direct filtered cross-space query returned "
        "no foreign rows. filtered mode shares one physical collection; the "
        "cross-space read must remain representable (finding 3) -- if this went "
        "clean, the shared-collection layout stopped being reachable and the "
        "negative example is gone."
    )
    assert all(r.payload.get("space_id") == SCOPE_SPACE for r in foreign_rows)
    assert SPACE_IDS == (SCOPE_SPACE, TARGET_SPACE)
