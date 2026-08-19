"""Unit tests for chancel.policy.PolicyGate — the security-critical module.

Every deny branch is covered explicitly; this file is the source of the
100% coverage requirement on src/chancel/policy.py.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from chancel.exceptions import ScopeViolation
from chancel.model import ActiveScope
from chancel.policy import PolicyGate

KNOWN_SPACES = ["alderman", "brightwater"]


def make_gate(**kwargs: object) -> PolicyGate:
    return PolicyGate(KNOWN_SPACES, **kwargs)  # type: ignore[arg-type]


class TestConstruction:
    def test_valid_known_spaces_construct(self) -> None:
        make_gate()

    @pytest.mark.parametrize("bad_space_id", ["Firm", "a b", "", "firm", "a" * 64, "UPPER"])
    def test_invalid_known_space_raises_value_error(self, bad_space_id: str) -> None:
        with pytest.raises(ValueError, match="invalid space_id"):
            PolicyGate(["alderman", bad_space_id])


class TestHappyPath:
    def test_firm_only(self) -> None:
        gate = make_gate()
        scope = ActiveScope(space_id="alderman")
        assert gate.authorize(scope, ["firm"]) == frozenset({"firm"})

    def test_space_only(self) -> None:
        gate = make_gate()
        scope = ActiveScope(space_id="alderman")
        assert gate.authorize(scope, ["space-alderman"]) == frozenset({"space-alderman"})

    def test_both(self) -> None:
        gate = make_gate()
        scope = ActiveScope(space_id="alderman")
        result = gate.authorize(scope, ["firm", "space-alderman"])
        assert result == frozenset({"firm", "space-alderman"})


class TestDefaultAllowlist:
    def test_returns_two_collection_set(self) -> None:
        gate = make_gate()
        scope = ActiveScope(space_id="alderman")
        assert gate.default_allowlist(scope) == frozenset({"firm", "space-alderman"})

    def test_unknown_space_denies(self) -> None:
        gate = PolicyGate(["alderman"])
        scope = ActiveScope(space_id="brightwater")
        with pytest.raises(ScopeViolation, match="unknown space"):
            gate.default_allowlist(scope)


class TestFailureMode1UnknownSpace:
    def test_unknown_space_denies(self) -> None:
        gate = PolicyGate(["alderman"])
        scope = ActiveScope(space_id="brightwater")
        with pytest.raises(ScopeViolation, match="unknown space") as exc_info:
            gate.authorize(scope, ["firm"])
        assert exc_info.value.space_id == "brightwater"
        assert exc_info.value.requested == ()
        assert exc_info.value.offending == ()


def _raising_generator() -> Iterator[str]:
    yield "firm"
    raise RuntimeError("boom mid-iteration")


class TestFailureMode2MalformedRequest:
    def test_empty_request_denies(self) -> None:
        gate = make_gate()
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation, match="empty request"):
            gate.authorize(scope, [])

    @pytest.mark.parametrize(
        "bad_requested",
        [
            ["*"],
            ["space-*"],
            [""],
            [" firm"],
            [42],
            [None],
        ],
        ids=["star", "space-star", "empty-elem", "leading-space", "int-elem", "none-elem"],
    )
    def test_malformed_elements_deny(self, bad_requested: list[object]) -> None:
        gate = make_gate()
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation, match="malformed request"):
            gate.authorize(scope, bad_requested)  # type: ignore[arg-type]

    def test_generator_that_raises_mid_iteration_denies_not_propagates(self) -> None:
        gate = make_gate()
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation, match="malformed request"):
            gate.authorize(scope, _raising_generator())

    def test_non_iterable_denies(self) -> None:
        gate = make_gate()
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation, match="malformed request"):
            gate.authorize(scope, 42)  # type: ignore[arg-type]


class TestFailureMode3ResolverTimeoutOrException:
    def test_resolver_raises_denies(self) -> None:
        def bad_resolver(scope: ActiveScope) -> frozenset[str]:
            raise RuntimeError("policy service is down")

        gate = make_gate(resolver=bad_resolver)
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation, match="policy resolution failed"):
            gate.authorize(scope, ["firm"])

    def test_slow_resolver_times_out(self) -> None:
        def slow_resolver(scope: ActiveScope) -> frozenset[str]:
            time.sleep(0.02)
            return scope.allowed_collections

        gate = make_gate(resolver=slow_resolver, timeout_s=0.001)
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation, match="policy resolution timed out"):
            gate.authorize(scope, ["firm"])


class TestFailureMode4MalformedOrEmptyAllowlist:
    def test_empty_allowlist_denies(self) -> None:
        def empty_resolver(scope: ActiveScope) -> frozenset[str]:
            return frozenset()

        gate = make_gate(resolver=empty_resolver)
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation, match="empty or malformed allowlist"):
            gate.authorize(scope, ["firm"])

    def test_non_set_return_denies(self) -> None:
        def list_resolver(scope: ActiveScope):  # type: ignore[no-untyped-def]
            return ["firm"]

        gate = make_gate(resolver=list_resolver)
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation, match="empty or malformed allowlist"):
            gate.authorize(scope, ["firm"])

    def test_allowlist_with_non_string_element_denies(self) -> None:
        def bad_resolver(scope: ActiveScope):  # type: ignore[no-untyped-def]
            return frozenset({"firm", 42})

        gate = make_gate(resolver=bad_resolver)
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation, match="empty or malformed allowlist"):
            gate.authorize(scope, ["firm"])

    def test_allowlist_with_empty_string_element_denies(self) -> None:
        def bad_resolver(scope: ActiveScope):  # type: ignore[no-untyped-def]
            return frozenset({"firm", ""})

        gate = make_gate(resolver=bad_resolver)
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation, match="empty or malformed allowlist"):
            gate.authorize(scope, ["firm"])


class TestFailureMode5ResolverExceedsAuthority:
    def test_resolver_cannot_widen_to_another_known_space(self) -> None:
        # The attack this branch exists to kill: a resolver returning a
        # *registered* space's collection is inside the gate's known-spaces
        # registry, so a check bounded by the registry alone would miss it.
        # The bound is scope.allowed_collections, so this must still deny.
        def widening_resolver(scope: ActiveScope) -> frozenset[str]:
            return frozenset({"firm", "space-alderman", "space-brightwater"})

        gate = PolicyGate(["alderman", "brightwater"], resolver=widening_resolver)
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation, match="resolver exceeded gate authority"):
            gate.authorize(scope, ["space-brightwater"])

    def test_resolver_returning_collection_for_unregistered_space_denies(self) -> None:
        # "space-camden" is a well-formed collection name, but camden is not
        # in this gate's known_spaces registry — also outside
        # scope.allowed_collections, so this fails the same branch.
        def escalating_resolver(scope: ActiveScope) -> frozenset[str]:
            return frozenset({"firm", "space-alderman", "space-camden"})

        gate = make_gate(resolver=escalating_resolver)
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation, match="resolver exceeded gate authority"):
            gate.authorize(scope, ["firm"])

    def test_resolver_returning_unknown_collection_denies(self) -> None:
        def escalating_resolver(scope: ActiveScope) -> frozenset[str]:
            return frozenset({"firm", "not-a-real-collection"})

        gate = make_gate(resolver=escalating_resolver)
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation, match="resolver exceeded gate authority"):
            gate.authorize(scope, ["firm"])

    def test_narrowing_resolver_is_honored(self) -> None:
        # A resolver may shrink authority relative to the scope's own
        # allowed_collections; that is ordinary policy, not an attack.
        def narrowing_resolver(scope: ActiveScope) -> frozenset[str]:
            return frozenset({"firm"})

        gate = make_gate(resolver=narrowing_resolver)
        scope = ActiveScope(space_id="alderman")
        assert gate.authorize(scope, ["firm"]) == frozenset({"firm"})
        with pytest.raises(ScopeViolation, match="requested collection outside active scope"):
            gate.authorize(scope, ["space-alderman"])


class TestFailureMode6RequestedOutsideAllowlist:
    def test_cross_space_request_is_denied_and_names_the_offender(self) -> None:
        gate = make_gate()
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation) as exc_info:
            gate.authorize(scope, ["firm", "space-brightwater"])
        assert exc_info.value.offending == ("space-brightwater",)
        assert "requested collection outside active scope" in str(exc_info.value)

    def test_offending_is_sorted_set_difference(self) -> None:
        gate = PolicyGate(["alderman", "brightwater", "camden"])
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation) as exc_info:
            gate.authorize(scope, ["space-camden", "space-brightwater"])
        assert exc_info.value.offending == ("space-brightwater", "space-camden")

    def test_no_partial_grant_one_bad_element_denies_whole_request(self) -> None:
        gate = make_gate()
        scope = ActiveScope(space_id="alderman")
        with pytest.raises(ScopeViolation):
            gate.authorize(scope, ["firm", "space-brightwater"])
