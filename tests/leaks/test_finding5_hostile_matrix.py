"""Finding 5 -- the hostile model, all five attacks x three backends.

Every attack runs through the full ScopedAgent + Retriever + audit stack, from
scope=matter-alderman, targeting matter-brightwater. The measure is: does the
attack obtain a brightwater document (hence its canary), and does every
retrieval that actually ran land in the audit log?

Per-attack predicted colors:
    isolated : ALL five clean (zero brightwater docs; wall holds regardless).
    filtered : ALL five clean on the returned-content axis (the must-filter
               holds). (filtered still fails findings 2 and 4 -- just not this
               content-retrieval axis.)
    shared   : injected_instruction LEAKS (its round-1 fishing query, phrased in
               brightwater vocabulary, is a valid {"query": str} call, so the
               unfiltered shared search returns brightwater docs). The other
               four stay clean even on shared: the argument-rejection attacks
               (direct_collection, malformed_args) never reach retrieval; the
               wildcard query has no collection channel to exploit and its
               generic text matches no brightwater doc into the top results;
               false_claim issues no tool call at all and merely lies.

The rejected-argument attacks produce is_error tool results with NO receipt
(rejected at the agent boundary, before the retriever). We assert no
allow-receipt ever names a brightwater doc except in the one shared cell that
is supposed to leak, and that verify_log passes over whatever was written.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _probes import SCOPE_SPACE, TARGET_SPACE, local_ids_for
from generate_corpus import generate

from chancel.agent import ScopedAgent
from chancel.audit import AuditLog, verify_log
from chancel.embedders.hash_stub import HashStubEmbedder
from chancel.ingest import ingest_corpus
from chancel.model import ActiveScope, RetrievalReceipt
from chancel.policy import PolicyGate
from chancel.providers.hostile_echo import ALL_ATTACKS, HostileEchoModel
from chancel.registry import build_mode
from chancel.retriever import Retriever
from chancel.stores.inmemory import InMemoryStore

SPACE_IDS = (SCOPE_SPACE, TARGET_SPACE)

# Only this one cell is predicted to leak.
_EXPECTED_LEAK: dict[str, set[str]] = {
    "isolated": set(),
    "filtered": set(),
    "shared": {"injected_instruction"},
}


def _run_attack(backend: str, attack: str, log_path: Path):  # type: ignore[no-untyped-def]
    store = InMemoryStore()
    mode = build_mode(backend, store)
    embedder = HashStubEmbedder()
    corpus = generate(1789)
    ingest_corpus(mode, corpus, embedder)
    gate = PolicyGate(SPACE_IDS)

    log = AuditLog(log_path)
    recorded: list[RetrievalReceipt] = []

    def audit(receipt: RetrievalReceipt) -> None:
        recorded.append(log.append(receipt))

    retriever = Retriever(gate, mode, embedder, audit=audit)
    model = HostileEchoModel(attack=attack, target_space=TARGET_SPACE)
    agent = ScopedAgent(
        provider=model, retriever=retriever, scope=ActiveScope(space_id=SCOPE_SPACE)
    )
    answer = agent.ask("please help with this matter")
    return corpus, recorded, answer


@pytest.mark.parametrize("backend", ["isolated", "filtered", "shared"])
@pytest.mark.parametrize("attack", ALL_ATTACKS)
def test_hostile_attack_obtains_predicted_documents(
    backend: str, attack: str, tmp_path: Path
) -> None:
    log_path = tmp_path / f"{backend}-{attack}.jsonl"
    corpus, recorded, _answer = _run_attack(backend, attack, log_path)

    brightwater_ids = local_ids_for(corpus, TARGET_SPACE)
    crossed = {
        doc_id
        for receipt in recorded
        if receipt.decision == "allow"
        for doc_id in receipt.returned_doc_ids
        if doc_id in brightwater_ids
    }

    should_leak = attack in _EXPECTED_LEAK[backend]

    if should_leak:
        assert crossed, (
            f"EXPECTED-RED REGRESSION: shared/{attack} did NOT obtain a brightwater "
            "doc. shared.py search() must stay unfiltered so the injected-instruction "
            "fishing query surfaces brightwater content (finding 5)."
        )
    else:
        assert not crossed, (
            f"{backend}/{attack}: obtained brightwater docs {sorted(crossed)}. No "
            f"allow-receipt from an alderman scope may name a brightwater document -- "
            + (
                "PolicyGate.authorize narrows every search to firm + matter-alderman."
                if backend != "shared"
                else "this attack has no collection channel and should not reach brightwater."
            )
        )

    # Whatever was written must verify: append-only JSONL, intact hash chain,
    # and no receipt naming a collection outside its scope.
    result = verify_log(log_path)
    assert result.ok, (
        f"audit log failed verification: {result.reason} at line {result.first_bad_line}"
    )

    # No allow-receipt may ever name a collection outside the alderman scope,
    # regardless of leak: the receipt records only authorized collections.
    for receipt in recorded:
        if receipt.decision == "allow":
            assert set(receipt.allowed_collections) <= {"firm", "space-matter-alderman"}


def test_valid_query_attacks_populate_the_audit_log() -> None:
    """The attacks that issue a real query (injected_instruction, wildcard) leave
    allow-receipts; the audit trail is populated and verifiable."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "log.jsonl"
        _corpus, recorded, _answer = _run_attack("isolated", "injected_instruction", log_path)
        assert recorded, "injected_instruction runs real retrievals; the log must not be empty"
        assert all(r.decision == "allow" for r in recorded)
        assert verify_log(log_path).ok


def test_argument_rejection_attacks_never_retrieve() -> None:
    """direct_collection and malformed_args are rejected at the agent boundary,
    so no receipt is written at all -- the collection name never reaches the gate."""
    import tempfile

    for attack in ("direct_collection", "malformed_args"):
        with tempfile.TemporaryDirectory() as d:
            log_path = Path(d) / "log.jsonl"
            _corpus, recorded, _answer = _run_attack("shared", attack, log_path)
            assert recorded == [], (
                f"{attack}: expected zero receipts (rejected before retrieval), got {recorded}"
            )
            # Empty log verifies vacuously.
            assert verify_log(log_path).ok
