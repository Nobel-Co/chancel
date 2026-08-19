"""Finding 6 -- the gate fails closed: six deliberate breakages, six denies.

Every breakage is exercised at the RETRIEVER level (the real entry point), so
each one both raises ``ScopeViolation`` AND leaves a single deny receipt in the
audit trail -- a failed authorization is never silent.

The six failure modes (PRP "Leak suite findings" #6, "PolicyGate must fail
CLOSED"):
    1. unknown space            -- scope not in the known-spaces registry
    2. empty allowlist          -- resolver hands back an empty set
    3. resolver raises          -- policy service throws
    4. resolver times out       -- policy service is too slow
    5. resolver returns garbage -- non-set / malformed allowlist (the internal
                                   "malformed request" path, simulated via the
                                   resolver seam)
    6. resolver exceeds scope   -- resolver returns another space's collection
"""

from __future__ import annotations

import time

import pytest
from _probes import RecordingAudit
from generate_corpus import generate

from chancel.embedders.hash_stub import HashStubEmbedder
from chancel.ingest import ingest_corpus
from chancel.model import ActiveScope
from chancel.policy import PolicyGate
from chancel.retriever import Retriever
from chancel.stores.inmemory import InMemoryStore
from chancel.stores.isolated import IsolatedStore

KNOWN = ("matter-alderman", "matter-brightwater")


def _retriever(gate: PolicyGate) -> tuple[Retriever, RecordingAudit]:
    store = InMemoryStore()
    mode = IsolatedStore(store)
    embedder = HashStubEmbedder()
    ingest_corpus(mode, generate(1789), embedder)
    audit = RecordingAudit()
    return Retriever(gate, mode, embedder, audit=audit), audit


def _assert_single_deny(audit: RecordingAudit, reason: str) -> None:
    denies = [r for r in audit.receipts if r.decision == "deny"]
    assert len(denies) == 1, f"expected exactly one deny receipt, got {audit.receipts}"
    assert denies[0].reason == reason
    assert not any(r.decision == "allow" for r in audit.receipts)


def test_breakage_1_unknown_space() -> None:
    gate = PolicyGate(KNOWN)
    retriever, audit = _retriever(gate)
    with pytest.raises(Exception) as exc:  # ScopeViolation
        retriever.retrieve(ActiveScope(space_id="matter-ghost"), "q")
    assert exc.value.reason == "unknown space"  # type: ignore[attr-defined]
    _assert_single_deny(audit, "unknown space")


def test_breakage_2_empty_allowlist() -> None:
    gate = PolicyGate(KNOWN, resolver=lambda scope: frozenset())
    retriever, audit = _retriever(gate)
    with pytest.raises(Exception) as exc:
        retriever.retrieve(ActiveScope(space_id="matter-alderman"), "q")
    assert exc.value.reason == "empty or malformed allowlist"  # type: ignore[attr-defined]
    _assert_single_deny(audit, "empty or malformed allowlist")


def test_breakage_3_resolver_raises() -> None:
    def boom(scope: ActiveScope) -> frozenset[str]:
        raise RuntimeError("policy service exploded")

    gate = PolicyGate(KNOWN, resolver=boom)
    retriever, audit = _retriever(gate)
    with pytest.raises(Exception) as exc:
        retriever.retrieve(ActiveScope(space_id="matter-alderman"), "q")
    assert exc.value.reason == "policy resolution failed"  # type: ignore[attr-defined]
    _assert_single_deny(audit, "policy resolution failed")


def test_breakage_4_resolver_times_out() -> None:
    def slow(scope: ActiveScope) -> frozenset[str]:
        time.sleep(0.02)
        return scope.allowed_collections

    gate = PolicyGate(KNOWN, resolver=slow, timeout_s=0.001)
    retriever, audit = _retriever(gate)
    with pytest.raises(Exception) as exc:
        retriever.retrieve(ActiveScope(space_id="matter-alderman"), "q")
    assert exc.value.reason == "policy resolution timed out"  # type: ignore[attr-defined]
    _assert_single_deny(audit, "policy resolution timed out")


def test_breakage_5_resolver_returns_garbage() -> None:
    # Not a set at all -- the malformed-allowlist branch. This is the internal
    # "malformed request" failure mode, reachable only by a misbehaving
    # resolver because the retriever itself never builds a bad request.
    gate = PolicyGate(KNOWN, resolver=lambda scope: ["firm"])  # type: ignore[arg-type,return-value]
    retriever, audit = _retriever(gate)
    with pytest.raises(Exception) as exc:
        retriever.retrieve(ActiveScope(space_id="matter-alderman"), "q")
    assert exc.value.reason == "empty or malformed allowlist"  # type: ignore[attr-defined]
    _assert_single_deny(audit, "empty or malformed allowlist")


def test_breakage_6_resolver_exceeds_scope() -> None:
    # Resolver tries to widen the scope to another matter's collection -- exactly
    # the cross-space read the gate exists to make impossible.
    def greedy(scope: ActiveScope) -> frozenset[str]:
        return frozenset({"firm", "space-matter-alderman", "space-matter-brightwater"})

    gate = PolicyGate(KNOWN, resolver=greedy)
    retriever, audit = _retriever(gate)
    with pytest.raises(Exception) as exc:
        retriever.retrieve(ActiveScope(space_id="matter-alderman"), "q")
    assert exc.value.reason == "resolver exceeded gate authority"  # type: ignore[attr-defined]
    _assert_single_deny(audit, "resolver exceeded gate authority")
