"""Finding 1 -- direct canary leak.

Each matter's corpus carries a distinctive canary string that appears in NO
other matter's documents. From inside one matter's active scope we issue a
query written in the *other* matter's distinctive vocabulary and ask: can the
other matter's canary be surfaced?

Predicted colors (PRP "Leak suite findings" #1):
    isolated  -> clean   (the collection IS the boundary)
    filtered  -> clean   (the must-filter stops direct content leak; filtered
                          fails findings 3-4, not this one)
    shared    -> leaked  (no filter at all -- the deliberate failure CI pins red)

Every retrieval goes through the real Retriever + PolicyGate stack.
"""

from __future__ import annotations

import pytest
from _probes import (
    SCOPE_SPACE,
    SPACE_IDS,
    TARGET_SPACE,
    build_stack,
    canary_for,
    local_ids_for,
)

from chancel.model import ActiveScope

# Vocabulary unique to each matter -- used to aim a query AT a matter without
# ever naming it or its collection.
_BRIGHTWATER_QUERY = "seaworthiness salvage award subrogation underwriter hull policy limit"
_ALDERMAN_QUERY = "fumigation phytosanitary demurrage containerized cargo contamination manifest"


def _retrieve_texts(backend: str, scope_space: str, query: str):  # type: ignore[no-untyped-def]
    stack = build_stack(backend)
    scope = ActiveScope(space_id=scope_space)
    chunks = stack.retriever.retrieve(scope, query, limit=20)
    texts = [c.text for c in chunks]
    returned_ids = {
        doc_id for receipt in stack.audit.receipts for doc_id in receipt.returned_doc_ids
    }
    return stack, chunks, texts, returned_ids


@pytest.mark.parametrize("backend", ["isolated", "filtered"])
def test_other_matter_canary_never_leaks_when_walled(backend: str) -> None:
    """isolated and filtered: the foreign canary is unreachable by content."""
    # Attacker sits in alderman, fishes for brightwater with brightwater vocab.
    stack, _chunks, texts, returned_ids = _retrieve_texts(backend, SCOPE_SPACE, _BRIGHTWATER_QUERY)
    brightwater_canary = canary_for(stack.corpus, TARGET_SPACE)
    brightwater_ids = local_ids_for(stack.corpus, TARGET_SPACE)

    assert not any(brightwater_canary in text for text in texts), (
        f"{backend}: brightwater canary appeared in a returned passage -- the "
        + (
            "collection boundary"
            if backend == "isolated"
            else "must-filter in filtered.py search()"
        )
        + " failed to exclude foreign content (finding 1)."
    )
    assert not (returned_ids & brightwater_ids), (
        f"{backend}: a brightwater document id was returned to an alderman scope; "
        "PolicyGate.authorize narrowed the search to firm + matter-alderman, so "
        "no brightwater point should be reachable."
    )

    # Symmetric direction: brightwater attacker fishing for alderman.
    stack2, _c2, texts2, returned2 = _retrieve_texts(backend, TARGET_SPACE, _ALDERMAN_QUERY)
    alderman_canary = canary_for(stack2.corpus, SCOPE_SPACE)
    alderman_ids = local_ids_for(stack2.corpus, SCOPE_SPACE)
    assert not any(alderman_canary in text for text in texts2), (
        f"{backend}: alderman canary leaked into a brightwater-scope retrieval."
    )
    assert not (returned2 & alderman_ids)


def test_shared_mode_leaks_the_other_matter_canary_by_design() -> None:
    """shared: the deliberate failure. The other matter's canary IS retrievable.

    DO NOT FIX shared.py to make this pass. The assertion is inverted on
    purpose: CI keeps `shared` red, and adding a filter to shared.py (turning
    it into filtered.py) would delete the negative example the suite needs.
    The mechanism is chancel/stores/shared.py: search() does `del authorized`
    and passes filter_logical=None, so every matter is in play for every query.
    """
    stack, _chunks, texts, returned_ids = _retrieve_texts("shared", SCOPE_SPACE, _BRIGHTWATER_QUERY)
    brightwater_canary = canary_for(stack.corpus, TARGET_SPACE)
    brightwater_ids = local_ids_for(stack.corpus, TARGET_SPACE)

    leaked_by_content = any(brightwater_canary in text for text in texts)
    leaked_by_id = bool(returned_ids & brightwater_ids)
    assert leaked_by_content, (
        "EXPECTED-RED REGRESSION: shared mode did NOT leak the brightwater canary. "
        "shared.py/search() must stay unfiltered (del authorized; filter_logical=None); "
        "if this went green, the suite stopped measuring finding 1."
    )
    assert leaked_by_id, (
        "EXPECTED-RED REGRESSION: shared mode returned no brightwater document id; "
        "the unfiltered search should surface brightwater points to an alderman scope."
    )


def test_scope_ids_are_the_two_matters() -> None:
    # Guardrail: the whole finding rests on these being distinct matters.
    assert SPACE_IDS == (SCOPE_SPACE, TARGET_SPACE)
    assert SCOPE_SPACE != TARGET_SPACE
