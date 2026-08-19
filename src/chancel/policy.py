"""The wall.

Every retrieval, from every provider, through every store backend, is a call
to PolicyGate.authorize(). Nothing reaches a vector store except through it.
This gate FAILS CLOSED: any exception, timeout, unknown space, empty
allowlist, or malformed input is a deny. Swapping the AI provider cannot
weaken this module because no provider touches it.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import cast

from chancel.exceptions import ScopeViolation
from chancel.model import ActiveScope, _validate_space_id


def _is_bad_collection_name(name: str) -> bool:
    return name == "" or "*" in name or "?" in name or any(c.isspace() for c in name)


class PolicyGate:
    """Fails closed. See module docstring for the invariant this upholds.

    A gate is constructed once with the registry of spaces that exist and,
    optionally, a resolver mapping an ActiveScope to its allowlist. The
    resolver defaults to ``ActiveScope.allowed_collections`` but exists as a
    seam so a deployment can back it with a policy service — and so this
    class has to defend against that service misbehaving.
    """

    def __init__(
        self,
        known_spaces: Iterable[str],
        *,
        resolver: Callable[[ActiveScope], frozenset[str]] | None = None,
        timeout_s: float = 1.0,
    ) -> None:
        spaces = tuple(known_spaces)
        for space_id in spaces:
            _validate_space_id(space_id)  # raises ValueError on garbage
        self._known_spaces: frozenset[str] = frozenset(spaces)
        self._resolver: Callable[[ActiveScope], frozenset[str]] = resolver or (
            lambda scope: scope.allowed_collections
        )
        self._timeout_s = timeout_s

    def default_allowlist(self, scope: ActiveScope) -> frozenset[str]:
        """The scope's own allowlist, with the same unknown-space check as authorize()."""
        if scope.space_id not in self._known_spaces:
            raise ScopeViolation("unknown space", scope.space_id, (), ())
        return scope.allowed_collections

    def authorize(self, scope: ActiveScope, requested: Iterable[str]) -> frozenset[str]:
        space_id = scope.space_id

        # 1. unknown space
        if space_id not in self._known_spaces:
            raise ScopeViolation("unknown space", space_id, (), ())

        # 2. malformed / empty request
        requested_tuple = self._materialize_requested(requested, space_id)

        # 3. resolver under timeout, wrapped so a misbehaving policy service
        # cannot crash or hang the gate into an open state.
        start = time.monotonic()
        try:
            raw_allowlist = self._resolver(scope)
        except Exception:
            raise ScopeViolation(
                "policy resolution failed", space_id, requested_tuple, ()
            ) from None
        elapsed = time.monotonic() - start
        if elapsed > self._timeout_s:
            # Post-hoc check: catches a slow resolver, not a hung one. A
            # truly hung resolver needs a process-level timeout.
            raise ScopeViolation("policy resolution timed out", space_id, requested_tuple, ())

        # 4. malformed / empty allowlist — a resolver cannot hand back
        # something the gate cannot reason about.
        if not isinstance(raw_allowlist, (set, frozenset)) or not raw_allowlist:
            raise ScopeViolation("empty or malformed allowlist", space_id, requested_tuple, ())
        if not all(isinstance(c, str) and c for c in raw_allowlist):
            raise ScopeViolation("empty or malformed allowlist", space_id, requested_tuple, ())
        allowlist = frozenset(raw_allowlist)

        # 5. a resolver can only shrink the scope's structural authority;
        # widening is unrepresentable here regardless of what the resolver
        # returns. The bound is scope.allowed_collections, not the gate's
        # known-spaces registry — a resolver returning another registered
        # space's collection is exactly the cross-space read this gate
        # exists to make impossible, and the registry alone would not catch
        # it.
        if not allowlist <= scope.allowed_collections:
            raise ScopeViolation("resolver exceeded gate authority", space_id, requested_tuple, ())

        # 6. every requested collection must be inside the allowlist. No
        # partial grants: one bad element denies the whole request, because
        # silent filtering would mask an attack — the leak suite requires
        # every attempt to surface as a deny, not a quietly-narrowed allow.
        offending = tuple(sorted(set(requested_tuple) - allowlist))
        if offending:
            raise ScopeViolation(
                "requested collection outside active scope",
                space_id,
                requested_tuple,
                offending,
            )

        return frozenset(requested_tuple)

    @staticmethod
    def _materialize_requested(requested: Iterable[str], space_id: str) -> tuple[str, ...]:
        # Materialized defensively: a generator that raises mid-iteration
        # denies rather than propagating past the gate.
        collected: list[object] = []
        try:
            for item in requested:
                collected.append(item)
        except Exception:
            raise ScopeViolation(
                "malformed request", space_id, tuple(str(x) for x in collected), ()
            ) from None

        if any(not isinstance(item, str) for item in collected):
            raise ScopeViolation(
                "malformed request", space_id, tuple(str(x) for x in collected), ()
            )

        str_items = cast(list[str], collected)
        if any(_is_bad_collection_name(item) for item in str_items):
            raise ScopeViolation("malformed request", space_id, tuple(str_items), ())

        if not str_items:
            # An empty request grants nothing. Callers wanting the scope's
            # full authority call default_allowlist() instead.
            raise ScopeViolation("empty request", space_id, (), ())

        return tuple(str_items)
