"""The importable leak-matrix runner behind ``chancel demo``.

This module builds the *real* stack -- ``registry.build_store`` /
``build_mode``, the ``hash_stub`` embedder, the generated synthetic corpus,
the full ``Retriever`` + ``PolicyGate`` + ``ScopedAgent`` path -- for every
(backend, provider) cell and records, per leak finding, the color the PRP
PREDICTS versus the color reality produced.

"Green" here does NOT mean "no leak." It means every cell behaved as
predicted: ``isolated`` clean, ``shared`` leaked-as-designed, ``filtered``
red on the findings it is supposed to be red on. ``MatrixReport.ok`` is True
exactly when reality matched the prediction in every cell; a ✗ is the alarm
-- it means a backend stopped behaving the way this repo claims it does.

Runs cold-clone: no API key, no Docker (``inmemory`` store), no downloads
(``hash_stub`` embedder). ``render_text(run_matrix())`` is literally the
table the README shows.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from chancel.agent import ScopedAgent
from chancel.corpus import generate
from chancel.embedders.hash_stub import HashStubEmbedder
from chancel.exceptions import ScopeViolation
from chancel.ingest import ingest_corpus
from chancel.model import ActiveScope, RetrievalReceipt, space_collection
from chancel.policy import PolicyGate
from chancel.providers.base import ChatModel
from chancel.providers.echo import EchoModel
from chancel.providers.hostile_echo import ATTACK_INJECTED_INSTRUCTION, HostileEchoModel
from chancel.registry import build_mode, build_provider, build_store
from chancel.retriever import Retriever
from chancel.stores.base import StorageMode, VectorStore

# The two matters in the synthetic corpus. The "attacker" runs inside
# ``SCOPE_SPACE`` and every finding measures whether ``TARGET_SPACE``'s data
# (which only ``TARGET_SPACE``'s canary lives in) can be made to cross.
SCOPE_SPACE = "matter-alderman"
TARGET_SPACE = "matter-brightwater"
SPACE_IDS = (SCOPE_SPACE, TARGET_SPACE)

# A question phrased entirely in the TARGET matter's distinctive vocabulary.
# Under ``shared`` an ``echo`` model queries with this verbatim and the
# unfiltered store hands back the other matter's documents; under
# ``isolated`` / ``filtered`` the same query cannot reach them.
_ADVERSARIAL_QUESTION = (
    "Summarize the seaworthiness exclusion, the salvage award, the hull "
    "repair costs, and the policy limit for the underwriter dispute."
)

Outcome = Literal["clean", "leaked", "denied", "n/a"]


class FindingResult(BaseModel, frozen=True):
    """One (finding, backend, provider) cell of the leak matrix."""

    finding: str
    backend: str
    provider: str
    outcome: Outcome
    expected: Outcome
    passed: bool
    detail: str


class MatrixReport(BaseModel, frozen=True):
    """The whole matrix. ``ok`` is True iff every cell matched its prediction."""

    results: tuple[FindingResult, ...]

    @property
    def ok(self) -> bool:
        return all(r.passed for r in self.results)

    def by_backend(self) -> dict[str, list[FindingResult]]:
        grouped: dict[str, list[FindingResult]] = {}
        for result in self.results:
            grouped.setdefault(result.backend, []).append(result)
        return grouped


# --------------------------------------------------------------------------
# corpus loading -- the generator is a module of this package (``chancel.corpus``),
# so it ships in the wheel and resolves identically from a source checkout and
# from site-packages.
# --------------------------------------------------------------------------


def load_corpus(seed: int = 1789) -> dict[str, list[dict[str, str | None]]]:
    """The generated synthetic corpus, as ``ingest_corpus`` expects it."""
    return generate(seed)


def target_local_ids(corpus: dict[str, list[dict[str, str | None]]]) -> frozenset[str]:
    """Every ``local_id`` that belongs to ``TARGET_SPACE``.

    Because the target matter's canary lives ONLY in target-matter documents,
    "a target ``local_id`` reached the agent" and "the canary is reachable"
    are the same event -- which is what the summary matrix measures.
    """
    return frozenset(str(doc["local_id"]) for doc in corpus.get(TARGET_SPACE, []))


# --------------------------------------------------------------------------
# stack construction -- one place, shared by every finding and by the tests.
# --------------------------------------------------------------------------


class _RecordingAudit:
    """Captures every receipt so a finding can inspect what was returned."""

    def __init__(self) -> None:
        self.receipts: list[RetrievalReceipt] = []

    def __call__(self, receipt: RetrievalReceipt) -> None:
        self.receipts.append(receipt)


@dataclass(frozen=True)
class MatrixStack:
    """Everything one matrix cell needs, wired and ingested."""

    backend: str
    store: VectorStore
    mode: StorageMode
    gate: PolicyGate
    embedder: HashStubEmbedder
    corpus: dict[str, list[dict[str, str | None]]]


def build_stack(
    backend: str,
    *,
    store_kind: str = "inmemory",
    sparse: bool = False,
    seed: int = 1789,
    location: str | None = None,
) -> MatrixStack:
    """Build and ingest one (backend, store) stack. ``sparse`` toggles whether
    sparse vectors are carried through ingest (dense ranking is always on)."""
    store = build_store(store_kind, location)
    mode = build_mode(backend, store)
    embedder = HashStubEmbedder()
    corpus = load_corpus(seed)
    if not sparse:
        # Suppress sparse vectors: ingest still runs, dense-only. Done by
        # wrapping the embedder so callers who asked for a dense-only stack
        # get one without a second embedder class.
        embedder = _DenseOnlyEmbedder()
    ingest_corpus(mode, corpus, embedder)
    gate = PolicyGate(SPACE_IDS)
    return MatrixStack(
        backend=backend, store=store, mode=mode, gate=gate, embedder=embedder, corpus=corpus
    )


class _DenseOnlyEmbedder(HashStubEmbedder):
    """``HashStubEmbedder`` with sparse disabled -- the default matrix runs
    dense-only so the summary does not depend on sparse being provisioned."""

    def embed_sparse(self, texts: Sequence[str]) -> None:
        return None


# --------------------------------------------------------------------------
# finding evaluators -- each returns (outcome, detail). Imported by the tests
# so the demo and the leak suite measure the identical thing.
# --------------------------------------------------------------------------


def _provider_for_canary(provider: str) -> ChatModel:
    """The model that drives the canary-leak probe for one provider column.

    ``hostile_echo`` uses its injected-instruction script (the one attack that
    fishes with the free-text query for the *other* matter's canary); every
    other provider drives a plain adversarial retrieval.
    """
    if provider == "hostile_echo":
        return HostileEchoModel(attack=ATTACK_INJECTED_INSTRUCTION, target_space=TARGET_SPACE)
    if provider == "echo":
        return EchoModel()
    return build_provider(provider)


def evaluate_canary_leak(stack: MatrixStack, provider: str) -> tuple[Outcome, str]:
    """Finding 1. Run the full agent as the ``SCOPE_SPACE`` attacker and check
    whether any ``TARGET_SPACE`` document (hence its canary) crossed.

    isolated/filtered -> clean (the wall / the filter hold on returned
    content); shared -> leaked (no filter at all).
    """
    audit = _RecordingAudit()
    retriever = Retriever(stack.gate, stack.mode, stack.embedder, audit=audit)
    model = _provider_for_canary(provider)
    agent = ScopedAgent(
        provider=model, retriever=retriever, scope=ActiveScope(space_id=SCOPE_SPACE)
    )
    answer = agent.ask(_ADVERSARIAL_QUESTION)

    target_ids = target_local_ids(stack.corpus)
    crossed_in_receipts = sorted(
        {
            doc_id
            for receipt in audit.receipts
            if receipt.decision == "allow"
            for doc_id in receipt.returned_doc_ids
            if doc_id in target_ids
        }
    )
    crossed_in_citations = sorted(set(answer.citations) & target_ids)
    crossed = sorted(set(crossed_in_receipts) | set(crossed_in_citations))

    if crossed:
        return (
            "leaked",
            f"{TARGET_SPACE} docs {crossed} reached the agent -- shared.py "
            "search() ignores `authorized` and passes filter_logical=None, so "
            "the other matter's canary is retrievable (finding 1).",
        )
    return (
        "clean",
        f"no {TARGET_SPACE} document reached the agent; every retrieval was "
        f"narrowed to {sorted(ActiveScope(space_id=SCOPE_SPACE).allowed_collections)} "
        "by PolicyGate.authorize().",
    )


def evaluate_unrepresentable(stack: MatrixStack) -> tuple[Outcome, str]:
    """Finding 3, summarized. Can a caller inside ``SCOPE_SPACE`` express a read
    of ``TARGET_SPACE``'s data?

    isolated -> denied: the gate raises for the foreign collection and there is
    no store call that names another space's collection.
    filtered/shared -> leaked: the single physical 'corpus' collection can be
    queried directly for the other matter's ``logical`` value (filtered) or
    with no filter at all (shared), and it returns foreign data.
    """
    foreign_collection = space_collection(TARGET_SPACE)
    if stack.backend == "isolated":
        try:
            stack.gate.authorize(ActiveScope(space_id=SCOPE_SPACE), (foreign_collection,))
        except ScopeViolation as exc:
            return (
                "denied",
                f"PolicyGate.authorize raised {exc.reason!r} for {foreign_collection!r}; "
                "IsolatedStore.search has no filter/collection parameter to smuggle it "
                "through either (retriever.py signature is {scope, query, limit}).",
            )
        return (
            "leaked",
            "UNEXPECTED: the isolated gate authorized a foreign collection.",
        )

    # filtered / shared: reach straight past the StorageMode into the shared
    # physical collection -- the freedom the translation site reintroduces.
    from chancel.stores.filtered import CORPUS_COLLECTION

    if stack.backend == "filtered":
        rows = stack.store.query(
            CORPUS_COLLECTION,
            None,
            None,
            filter_logical=foreign_collection,
            limit=100,
        )
    else:  # shared
        rows = stack.store.query(CORPUS_COLLECTION, None, None, filter_logical=None, limit=100)
    foreign_rows = [r for r in rows if r.payload.get("space_id") == TARGET_SPACE]
    if foreign_rows:
        return (
            "leaked",
            f"store.query({CORPUS_COLLECTION!r}, filter_logical={foreign_collection!r}) "
            f"returned {len(foreign_rows)} {TARGET_SPACE} point(s) from a {stack.backend} "
            "context -- the cross-space read is representable (finding 3).",
        )
    return ("clean", "UNEXPECTED: no foreign rows returned from the shared collection.")


def evaluate_deletion(stack: MatrixStack) -> tuple[Outcome, str]:
    """Finding 4, summarized. After deleting ``TARGET_SPACE``, is the deletion
    verifiable independently of the query path under test?

    isolated -> clean: list_collections() is external to the query mechanism.
    filtered/shared -> leaked: the only available check re-runs the very filter
    it is meant to certify, so it cannot prove deletion.
    """
    stack.mode.delete_space(TARGET_SPACE)
    report = stack.mode.verify_deletion(TARGET_SPACE)
    if report.independent_of_query_path:
        return (
            "clean",
            f"verify_deletion used {report.method!r}, external to the query path; "
            "deletion is certifiable without trusting the mechanism under test.",
        )
    return (
        "leaked",
        f"verify_deletion used {report.method!r}, the SAME filter/query path "
        "search() uses; it cannot independently certify deletion -- rows may be "
        "gone but you must trust the filter to believe it (finding 4).",
    )


# --------------------------------------------------------------------------
# the predictions -- the PRP's expected color for each cell.
# --------------------------------------------------------------------------

_CANARY_EXPECTED: dict[str, Outcome] = {
    "isolated": "clean",
    "filtered": "clean",
    "shared": "leaked",
}
_UNREPRESENTABLE_EXPECTED: dict[str, Outcome] = {
    "isolated": "denied",
    "filtered": "leaked",
    "shared": "leaked",
}
_DELETION_EXPECTED: dict[str, Outcome] = {
    "isolated": "clean",
    "filtered": "leaked",
    "shared": "leaked",
}


def run_matrix(
    *,
    providers: Sequence[str] = ("echo", "hostile_echo"),
    backends: Sequence[str] = ("isolated", "filtered", "shared"),
    store_kind: str = "inmemory",
    sparse: bool = False,
    seed: int = 1789,
) -> MatrixReport:
    """Build every (backend, provider) cell and record predicted vs actual color.

    The canary-leak finding is evaluated per provider (the model participates);
    the unrepresentable and deletion findings are provider-independent and are
    recorded once per backend with provider ``"n/a"``.
    """
    results: list[FindingResult] = []

    for backend in backends:
        # One freshly-ingested stack per provider for the canary probe, so the
        # agent's per-run state (and, under shared, its retrievals) never bleed
        # between provider columns.
        for provider in providers:
            stack = build_stack(backend, store_kind=store_kind, sparse=sparse, seed=seed)
            outcome, detail = evaluate_canary_leak(stack, provider)
            expected = _CANARY_EXPECTED[backend]
            results.append(
                FindingResult(
                    finding="canary-leak",
                    backend=backend,
                    provider=provider,
                    outcome=outcome,
                    expected=expected,
                    passed=outcome == expected,
                    detail=detail,
                )
            )

        # Provider-independent findings: one fresh stack each (deletion mutates).
        unrep_stack = build_stack(backend, store_kind=store_kind, sparse=sparse, seed=seed)
        outcome, detail = evaluate_unrepresentable(unrep_stack)
        expected = _UNREPRESENTABLE_EXPECTED[backend]
        results.append(
            FindingResult(
                finding="unrepresentable-call",
                backend=backend,
                provider="n/a",
                outcome=outcome,
                expected=expected,
                passed=outcome == expected,
                detail=detail,
            )
        )

        del_stack = build_stack(backend, store_kind=store_kind, sparse=sparse, seed=seed)
        outcome, detail = evaluate_deletion(del_stack)
        expected = _DELETION_EXPECTED[backend]
        results.append(
            FindingResult(
                finding="deletion-verifiability",
                backend=backend,
                provider="n/a",
                outcome=outcome,
                expected=expected,
                passed=outcome == expected,
                detail=detail,
            )
        )

    return MatrixReport(results=tuple(results))


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

_MARK = {True: "✓", False: "✗"}  # ✓ / ✗


def _row_cells(r: FindingResult) -> tuple[str, str, str, str, str, str]:
    return (
        r.finding,
        r.backend,
        r.provider,
        r.expected,
        r.outcome,
        _MARK[r.passed],
    )


def render_text(report: MatrixReport) -> str:
    """Human table: predicted vs actual color per cell, with a PASS/FAIL summary.

    PASS means every prediction held -- INCLUDING the reds being red. FAIL is
    the alarm: some backend diverged from what this repo claims about it.
    """
    header = ("finding", "backend", "provider", "expected", "actual", "ok")
    rows = [_row_cells(r) for r in report.results]
    widths = [
        max(len(header[i]), max((len(row[i]) for row in rows), default=0))
        for i in range(len(header))
    ]

    def fmt(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = [fmt(header), fmt(tuple("-" * w for w in widths))]
    lines.extend(fmt(row) for row in rows)

    passed = sum(1 for r in report.results if r.passed)
    total = len(report.results)
    summary = "PASS" if report.ok else "FAIL"
    lines.append("")
    lines.append(
        f"{summary}: {passed}/{total} cells matched their predicted color "
        "(PASS = isolated clean, shared leaked-by-design, filtered red where predicted)."
    )
    return "\n".join(lines)


def render_github(report: MatrixReport) -> str:
    """GitHub-flavored markdown table for ``$GITHUB_STEP_SUMMARY``."""
    passed = sum(1 for r in report.results if r.passed)
    total = len(report.results)
    summary = "PASS" if report.ok else "FAIL"

    lines = [
        f"### chancel leak matrix: **{summary}** ({passed}/{total} cells matched prediction)",
        "",
        "| finding | backend | provider | expected | actual | ok |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in report.results:
        lines.append(
            f"| {r.finding} | {r.backend} | {r.provider} | {r.expected} | "
            f"{r.outcome} | {_MARK[r.passed]} |"
        )
    lines.append("")
    lines.append(
        "_PASS means every predicted color held, including the deliberate reds: "
        "`shared` leaks by design and `filtered` fails findings 3-4. A ✗ is the alarm._"
    )
    return "\n".join(lines)
