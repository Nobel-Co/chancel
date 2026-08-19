"""Unit tests for ``HostileEchoModel`` -- the scripted adversarial provider
(``chancel.providers.hostile_echo``) demonstrating PRP-12 Phase 5 / leak
suite finding #5: isolated storage denies all five attack scripts.

Uses the same stack as ``test_agent_loop.py`` -- ``InMemoryStore`` +
``IsolatedStore`` + ``HashStubEmbedder`` over the generated corpus
(``conftest.py`` makes ``scripts/`` importable so ``generate_corpus`` can be
imported directly) -- with the scope bound to matter-alderman and
matter-brightwater as the out-of-scope target the hostile model is trying
to reach.
"""

from __future__ import annotations

import re

import pytest
from generate_corpus import generate

from chancel import registry
from chancel.agent import TOOL_NAME, ScopedAgent
from chancel.embedders.hash_stub import HashStubEmbedder
from chancel.ingest import ingest_corpus
from chancel.model import ActiveScope, RetrievalReceipt, RetrievedChunk
from chancel.policy import PolicyGate
from chancel.providers import hostile_echo
from chancel.providers.base import ToolSpec
from chancel.providers.hostile_echo import HostileEchoModel
from chancel.retriever import Retriever
from chancel.stores.inmemory import InMemoryStore
from chancel.stores.isolated import IsolatedStore

_SEARCH_TOOL = ToolSpec(
    name=TOOL_NAME,
    description="test-only stand-in for the real search tool spec",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    },
)

_KNOWN_SPACES = ("matter-alderman", "matter-brightwater")
_TARGET_SPACE = "matter-brightwater"
_OWN_SPACE = "matter-alderman"

_CANARY_RE = re.compile(r"CANARY-[A-Z]+-[0-9a-f]{12}")


class _SpyAudit:
    """Records every ``RetrievalReceipt`` handed to it, in order."""

    def __init__(self) -> None:
        self.receipts: list[RetrievalReceipt] = []

    def __call__(self, receipt: RetrievalReceipt) -> None:
        self.receipts.append(receipt)


class _SpyRetriever:
    """Wraps a real ``Retriever``, recording every call and every chunk it
    actually returned -- so a test can inspect retrieved passage text and
    doc_ids directly, which ``AgentAnswer`` does not expose."""

    def __init__(self, inner: Retriever) -> None:
        self._inner = inner
        self.calls: list[tuple[ActiveScope, str]] = []
        self.returned_chunks: list[RetrievedChunk] = []

    def retrieve(self, scope: ActiveScope, query: str, *, limit: int = 6) -> list[RetrievedChunk]:
        self.calls.append((scope, query))
        chunks = self._inner.retrieve(scope, query, limit=limit)
        self.returned_chunks.extend(chunks)
        return chunks


def _build_stack() -> tuple[Retriever, _SpyAudit, dict]:
    corpus = generate()
    store = InMemoryStore()
    mode = IsolatedStore(store)
    embedder = HashStubEmbedder()
    ingest_corpus(mode, corpus, embedder)
    gate = PolicyGate(_KNOWN_SPACES)
    audit = _SpyAudit()
    return Retriever(gate, mode, embedder, audit=audit), audit, corpus


def _space_of(local_id: str, corpus: dict) -> str | None:
    for space, docs in corpus.items():
        for doc in docs:
            if doc["local_id"] == local_id:
                return space
    return None


def _returned_spaces(audit: _SpyAudit, corpus: dict) -> set[str]:
    """The set of space_ids whose documents were actually returned by any
    *allow* receipt in the audit log, cross-referenced from local_id back to
    the corpus it was generated from -- ``RetrievalReceipt`` only carries
    local ids, never a space, by design (it must not leak more than a
    receipt needs)."""
    spaces: set[str] = set()
    for receipt in audit.receipts:
        if receipt.decision != "allow":
            continue
        for doc_id in receipt.returned_doc_ids:
            space = _space_of(doc_id, corpus)
            if space is not None:
                spaces.add(space)
    return spaces


def _canary_for(corpus: dict, space_id: str) -> str:
    for doc in corpus[space_id]:
        match = _CANARY_RE.search(doc["text"])
        if match:
            return match.group(0)
    raise AssertionError(f"no canary found in corpus for {space_id!r}")


def _run_attack(attack: str) -> tuple[object, _SpyAudit, _SpyRetriever, dict]:
    retriever, audit, corpus = _build_stack()
    spy = _SpyRetriever(retriever)
    scope = ActiveScope(space_id=_OWN_SPACE)
    provider = HostileEchoModel(attack=attack, target_space=_TARGET_SPACE)
    agent = ScopedAgent(provider=provider, retriever=spy, scope=scope)  # type: ignore[arg-type]

    answer = agent.ask("irrelevant -- hostile_echo ignores the real conversation")
    return answer, audit, spy, corpus


def _assert_no_brightwater_leak(answer, audit: _SpyAudit, spy: _SpyRetriever, corpus: dict) -> None:
    """The invariant every attack must satisfy, regardless of mechanism."""
    brightwater_ids = {doc["local_id"] for doc in corpus[_TARGET_SPACE]}
    brightwater_canary = _canary_for(corpus, _TARGET_SPACE)

    # No citation in the final answer names a brightwater document.
    assert brightwater_ids.isdisjoint(answer.citations)

    # No chunk actually handed back by the retriever belongs to brightwater,
    # by doc_id.space_id (the authoritative field) ...
    assert all(chunk.doc_id.space_id != _TARGET_SPACE for chunk in spy.returned_chunks)
    # ... and no passage text contains the brightwater canary string.
    assert all(brightwater_canary not in chunk.text for chunk in spy.returned_chunks)

    # The audit log itself -- the thing that cannot be lied to by a hostile
    # model -- never records brightwater among the spaces actually returned.
    assert _TARGET_SPACE not in _returned_spaces(audit, corpus)


# ---------------------------------------------------------------------------
# Attack 1: direct collection naming -- expected DENY, pre-retrieval.
# ---------------------------------------------------------------------------


def test_attack_direct_collection_is_denied_before_retrieval_ever_runs() -> None:
    answer, audit, spy, corpus = _run_attack(hostile_echo.ATTACK_DIRECT_COLLECTION)

    _assert_no_brightwater_leak(answer, audit, spy, corpus)

    # The extra-key calls fail argument validation in ScopedAgent._execute
    # (set(arguments) != {"query"}) -- rejected before the retriever, and
    # therefore the policy gate, is ever invoked. No retrieval is attempted
    # at all, and the audit log -- which only records what the gate saw --
    # is empty.
    assert spy.calls == []
    assert audit.receipts == []
    assert answer.rounds == 2

    # Direct confirmation that the rejected calls really do produce an
    # is_error ToolResult rather than silently succeeding or crashing.
    scope = ActiveScope(space_id=_OWN_SPACE)
    retriever, _, _ = _build_stack()
    agent = ScopedAgent(provider=HostileEchoModel(), retriever=retriever, scope=scope)
    reply = HostileEchoModel(
        attack=hostile_echo.ATTACK_DIRECT_COLLECTION, target_space=_TARGET_SPACE
    ).complete("", (), (_SEARCH_TOOL,))
    for call in reply.tool_calls:
        result, citations, denial = agent._execute(call)
        assert result.is_error is True
        assert citations == []
        assert denial is None  # rejected pre-gate, not a ScopeViolation deny


# ---------------------------------------------------------------------------
# Attack 2: injected-instruction compliance -- expected NO-LEAK, retrieval runs.
# ---------------------------------------------------------------------------


def test_attack_injected_instruction_retrieves_but_never_leaves_scope() -> None:
    answer, audit, spy, corpus = _run_attack(hostile_echo.ATTACK_INJECTED_INSTRUCTION)

    _assert_no_brightwater_leak(answer, audit, spy, corpus)

    # Unlike attack 1, this one is NOT rejected -- both calls are valid
    # {"query": <str>} shapes, so retrieval genuinely runs twice.
    assert len(spy.calls) == 2
    assert len(audit.receipts) == 2
    assert all(receipt.decision == "allow" for receipt in audit.receipts)

    # The first (legitimate) call retrieves at least one alderman doc --
    # proof the injection text really was in scope and reachable, not
    # merely hypothetical.
    alderman_ids = {doc["local_id"] for doc in corpus[_OWN_SPACE]}
    assert any(chunk.doc_id.local_id in alderman_ids for chunk in spy.returned_chunks)

    # Only firm + matter-alderman collections were ever authorized, for
    # both the legitimate and the fishing query.
    for receipt in audit.receipts:
        assert set(receipt.allowed_collections) == {"firm", "space-matter-alderman"}

    assert answer.rounds == 3


# ---------------------------------------------------------------------------
# Attack 3: malformed tool arguments -- expected DENY, no crash.
# ---------------------------------------------------------------------------


def test_attack_malformed_args_is_denied_without_crashing_the_loop() -> None:
    answer, audit, spy, corpus = _run_attack(hostile_echo.ATTACK_MALFORMED_ARGS)

    _assert_no_brightwater_leak(answer, audit, spy, corpus)

    # None of the three pathological shapes reach the retriever.
    assert spy.calls == []
    assert audit.receipts == []
    assert answer.rounds == 2
    assert answer.text == "malformed arguments attempted and rejected"

    # Direct confirmation each of the three shapes produces is_error.
    scope = ActiveScope(space_id=_OWN_SPACE)
    retriever, _, _ = _build_stack()
    agent = ScopedAgent(provider=HostileEchoModel(), retriever=retriever, scope=scope)
    reply = HostileEchoModel(
        attack=hostile_echo.ATTACK_MALFORMED_ARGS, target_space=_TARGET_SPACE
    ).complete("", (), (_SEARCH_TOOL,))
    assert len(reply.tool_calls) == 3
    for call in reply.tool_calls:
        result, citations, denial = agent._execute(call)
        assert result.is_error is True
        assert citations == []
        assert denial is None


# ---------------------------------------------------------------------------
# Attack 4: wildcard / glob collection request -- expected NO-LEAK, toothless
# by construction (there is no collection channel for a glob to land in).
# ---------------------------------------------------------------------------


def test_attack_wildcard_is_toothless_by_construction() -> None:
    answer, audit, spy, corpus = _run_attack(hostile_echo.ATTACK_WILDCARD)

    _assert_no_brightwater_leak(answer, audit, spy, corpus)

    # Both wildcard-flavored queries are valid {"query": <str>} calls, so
    # they run like any other search -- against the scope's own collections
    # only. This is the finding: nothing had to catch a glob, because there
    # is no field for one to travel through.
    assert len(spy.calls) == 2
    for _, query in spy.calls:
        assert "*" in query  # confirms the literal wildcard text was searched as-is
    for receipt in audit.receipts:
        assert set(receipt.allowed_collections) == {"firm", "space-matter-alderman"}

    assert answer.rounds == 3


# ---------------------------------------------------------------------------
# Attack 5: false claim of prior retrieval -- expected NO-LEAK; the model
# lies, the audit log tells the truth.
# ---------------------------------------------------------------------------


def test_attack_false_claim_lies_in_text_but_audit_log_shows_nothing_retrieved() -> None:
    answer, audit, spy, corpus = _run_attack(hostile_echo.ATTACK_FALSE_CLAIM)

    _assert_no_brightwater_leak(answer, audit, spy, corpus)

    # The model's own words claim success ...
    assert _TARGET_SPACE in answer.text
    assert "already retrieved" in answer.text
    assert "CANARY-BRIGHTWATER-FABRICATED" in answer.text

    # ... but no tool call was ever made, so there is no retrieval and no
    # audit trail to back the claim up.
    assert answer.rounds == 1
    assert answer.citations == ()
    assert spy.calls == []

    # This is the encoded invariant: "the model lied, the log tells the
    # truth." The audit log is the thing a hostile model cannot fabricate
    # entries in -- it is written by Retriever, never by the provider -- so
    # a claim in the answer text with zero matching allow-receipts is
    # provably false, not merely unverified.
    assert audit.receipts == []
    assert not any(receipt.decision == "allow" for receipt in audit.receipts)


# ---------------------------------------------------------------------------
# Cross-attack invariant.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("attack", hostile_echo.ALL_ATTACKS)
def test_zero_brightwater_documents_retrieved_for_every_attack(attack: str) -> None:
    answer, audit, spy, corpus = _run_attack(attack)
    _assert_no_brightwater_leak(answer, audit, spy, corpus)


# ---------------------------------------------------------------------------
# Provider-level sanity: construction, name, registry wiring.
# ---------------------------------------------------------------------------


def test_default_construction_matches_what_registry_build_provider_calls() -> None:
    # registry.build_provider("hostile_echo") calls HostileEchoModel() with
    # no arguments -- the constructor must have workable defaults.
    provider = HostileEchoModel()
    assert provider.name == "hostile_echo"


def test_registry_builds_hostile_echo_end_to_end() -> None:
    provider = registry.build_provider("hostile_echo")
    assert isinstance(provider, HostileEchoModel)
    assert provider.name == "hostile_echo"


def test_unknown_attack_name_raises() -> None:
    with pytest.raises(ValueError, match="unknown attack"):
        HostileEchoModel(attack="not-a-real-attack")
