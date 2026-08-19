"""Three-tier memory and the firm-promotion gate.

INVARIANT (the one this module defends):
    A fact may be promoted matter -> firm ONLY if every provenance id it cites
    belongs to the firm corpus. If even one provenance id is space-scoped, the
    promotion is refused, and the refusal NAMES the first offending
    space-scoped id. This is the memory-tier analogue of the retrieval wall:
    firm memory crosses every space, so a space-scoped fact laundered into it
    would leak that space's data into every other matter's context. The gate
    below makes that laundering unrepresentable at the promotion boundary --
    there is no "promote anyway" flag, exactly as there is no collection
    parameter on the retriever.

Memory tiers (see ``chancel.model.Scope`` for the retrieval-side analogue):
    - personal : crosses spaces (a user's own notes). Not promotable *into*;
                 it is already the widest tier a single user sees.
    - firm     : crosses every space (playbooks, house style). The tier a
                 promotion targets, and the one whose provenance must be clean.
    - matter   : never leaves its space. The tier a space-scoped fact lives in,
                 and the tier ``promote_fact`` refuses to launder from.

This module is deliberately small: it holds the tier vocabulary and the one
gate, nothing else. No retrieval, no store, no provider -- promotion is a
policy decision over ``DocumentId`` provenance, and a ``DocumentId`` already
knows its own scope (``chancel.model``), so the gate is a scope check, not a
lookup.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, Field

from chancel.exceptions import PromotionRefused
from chancel.model import DocumentId, Scope


class MemoryTier(StrEnum):
    """The three tiers a remembered fact can live in. See module docstring."""

    PERSONAL = "personal"
    FIRM = "firm"
    MATTER = "matter"


class FirmMemoryEntry(BaseModel, frozen=True):
    """A fact that has cleared the promotion gate and now lives at firm tier.

    Immutable: the provenance is frozen at promotion time so a later mutation
    cannot retroactively admit a space-scoped source the gate rejected.
    """

    tier: MemoryTier = MemoryTier.FIRM
    fact_text: str = Field(min_length=1)
    provenance: tuple[DocumentId, ...] = Field(min_length=1)


def promote_fact(fact_text: str, provenance: Sequence[DocumentId]) -> FirmMemoryEntry:
    """Promote a fact to firm tier iff EVERY provenance id is firm-scoped.

    Fails closed: an empty provenance is refused (a firm fact with no firm
    source is exactly the unsourced claim the gate exists to stop), and the
    FIRST space-scoped provenance id encountered refuses the whole promotion,
    naming that id in the raised ``PromotionRefused``.

    The scan is in input order so "first offending" is well-defined and a test
    can assert the named id is a real element of the input, not a synthesized
    string.
    """
    if not provenance:
        raise PromotionRefused(
            "cannot promote a fact with no provenance; a firm fact needs a firm source",
            (),
        )

    for doc_id in provenance:
        if doc_id.scope is Scope.SPACE:
            # Name the first offender and stop. We report its collection-qualified
            # local id so the refusal points at a specific space document, not
            # just "some space id".
            offender = f"{doc_id.collection}:{doc_id.local_id}"
            raise PromotionRefused(
                "provenance includes a space-scoped document; matter data cannot "
                "be laundered into firm memory",
                (offender,),
            )

    return FirmMemoryEntry(fact_text=fact_text, provenance=tuple(provenance))
