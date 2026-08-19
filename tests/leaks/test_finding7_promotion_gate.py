"""Finding 7 -- the firm-promotion gate, property-tested.

``promote_fact`` (chancel.memory) enforces: a fact promotes to firm tier IFF
every provenance id is firm-scoped. If ANY provenance id is space-scoped, it
refuses, naming the FIRST offending space-scoped id. Firm memory crosses every
space, so a single space-scoped source laundered in would leak that matter's
data into every other matter's context -- the memory-tier analogue of the
retrieval wall.

Property (Hypothesis, over generated mixed provenance sets):
    - all-firm provenance  -> succeeds, and the entry keeps that provenance.
    - any space-scoped id  -> PromotionRefused, and the named offender is a REAL
                              space-scoped element of the input (in input order).
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chancel.exceptions import PromotionRefused
from chancel.memory import FirmMemoryEntry, MemoryTier, promote_fact
from chancel.model import DocumentId, Scope, space_collection

_SPACE_IDS = st.sampled_from(["matter-alderman", "matter-brightwater", "matter-caruso"])
_LOCAL_IDS = st.text(alphabet="abcdefghijklmnop0123456789", min_size=1, max_size=6)


@st.composite
def firm_ids(draw: st.DrawFn) -> DocumentId:
    return DocumentId(scope=Scope.FIRM, space_id=None, local_id=draw(_LOCAL_IDS))


@st.composite
def space_ids(draw: st.DrawFn) -> DocumentId:
    return DocumentId(scope=Scope.SPACE, space_id=draw(_SPACE_IDS), local_id=draw(_LOCAL_IDS))


@given(provenance=st.lists(firm_ids(), min_size=1, max_size=8))
def test_all_firm_provenance_promotes(provenance: list[DocumentId]) -> None:
    entry = promote_fact("firms may always cite firm sources", provenance)
    assert isinstance(entry, FirmMemoryEntry)
    assert entry.tier is MemoryTier.FIRM
    assert entry.provenance == tuple(provenance)


@given(
    firm=st.lists(firm_ids(), max_size=6),
    space=st.lists(space_ids(), min_size=1, max_size=6),
    seed=st.randoms(use_true_random=False),
)
def test_any_space_scoped_provenance_is_refused_and_named(
    firm: list[DocumentId], space: list[DocumentId], seed: object
) -> None:
    # Interleave firm and space ids into an arbitrary order.
    provenance = firm + space
    import random as _random

    rng = _random.Random(repr(seed))
    rng.shuffle(provenance)

    with pytest.raises(PromotionRefused) as excinfo:
        promote_fact("a fact citing at least one matter document", provenance)

    # Exactly one offender is named, and it is the FIRST space-scoped id in
    # input order, reported as its collection-qualified local id.
    offending = excinfo.value.offending_ids
    assert len(offending) == 1
    first_space = next(d for d in provenance if d.scope is Scope.SPACE)
    expected = f"{space_collection(first_space.space_id or '')}:{first_space.local_id}"
    assert offending[0] == expected

    # The named offender corresponds to a real space-scoped element of the input.
    space_qualified = {
        f"{space_collection(d.space_id or '')}:{d.local_id}"
        for d in provenance
        if d.scope is Scope.SPACE
    }
    assert offending[0] in space_qualified


def test_empty_provenance_is_refused() -> None:
    # Fails closed: a firm fact with no firm source is the unsourced claim the
    # gate exists to stop.
    with pytest.raises(PromotionRefused):
        promote_fact("unsourced", [])


def test_single_space_id_names_that_id() -> None:
    doc = DocumentId(scope=Scope.SPACE, space_id="matter-alderman", local_id="a4")
    with pytest.raises(PromotionRefused) as excinfo:
        promote_fact("cite a matter doc", [doc])
    assert excinfo.value.offending_ids == ("space-matter-alderman:a4",)
