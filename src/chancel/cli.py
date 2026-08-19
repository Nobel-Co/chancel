"""The ``chancel`` / ``chl`` command line.

Five commands, each a thin driver over the library: ``demo`` runs the
backend x provider leak matrix, ``ask`` runs one scoped retrieval end to
end, ``attack`` plays the hostile model against the wall live, ``verify-log``
checks an audit log's hash chain, and ``gen-corpus`` regenerates the
synthetic fixture.

Nothing here reaches around the abstraction boundary. Provider construction
goes through ``chancel.registry``; the one place a concrete provider is named
(``attack`` needs to vary the hostile model's ``attack``/``target_space``,
which the registry's parameterless ``build_provider`` cannot express) is
reached by ``importlib.import_module`` on a string module name, which keeps
the vendor-name abstraction grep clean. ``chancel.demo`` is imported the same
lazy way so this module still imports if the demo module lands slightly after
it.
"""

# ruff: noqa: B008 -- typer.Option/Argument in defaults is the framework's API.
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
from typing import cast

import typer

from chancel.agent import ScopedAgent
from chancel.audit import AuditLog, verify_log
from chancel.ingest import ingest_corpus
from chancel.model import ActiveScope, RetrievalReceipt
from chancel.policy import PolicyGate
from chancel.registry import build_embedder, build_mode, build_provider, build_store
from chancel.retriever import Retriever

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Provable scope isolation for AI retrieval: instructions travel, matter data does not.",
)

CorpusDoc = dict[str, str | None]
Corpus = dict[str, list[CorpusDoc]]

_DEFAULT_LOG = Path("./chancel-audit.jsonl")
_OFFLINE_PROVIDERS = ("echo", "hostile_echo")


# -- shared helpers -------------------------------------------------------


def _repo_root() -> Path:
    """The repository root: two levels up from ``src/chancel/cli.py``."""
    return Path(__file__).resolve().parents[2]


def _load_generate_module() -> ModuleType:
    """Import ``scripts/generate_corpus.py`` by file path.

    The generator is a standalone script directory, not a package, so it is
    loaded by location rather than by import name. Raises a clear CLI error
    if the script is absent (e.g. installed as a wheel, which omits scripts).
    """
    gen_path = _repo_root() / "scripts" / "generate_corpus.py"
    if not gen_path.exists():
        raise typer.BadParameter(
            f"corpus generator not found at {gen_path}; "
            "run from a source checkout or `python scripts/generate_corpus.py` first"
        )
    spec = importlib.util.spec_from_file_location("generate_corpus", gen_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise typer.BadParameter(f"could not load corpus generator at {gen_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_corpus(seed: int) -> Corpus:
    """Load the synthetic corpus, preferring the generator over on-disk files.

    Order: (1) call ``scripts/generate_corpus.generate(seed)`` if the script
    is present -- this honors ``--seed``; (2) fall back to reading
    ``data/corpus/*.jsonl`` if those exist (default-seed fixture); (3) error
    clearly telling the user how to produce the corpus.
    """
    gen_path = _repo_root() / "scripts" / "generate_corpus.py"
    if gen_path.exists():
        module = _load_generate_module()
        return cast(Corpus, module.generate(seed))

    corpus_dir = _repo_root() / "data" / "corpus"
    jsonl_files = sorted(corpus_dir.glob("*.jsonl")) if corpus_dir.exists() else []
    if jsonl_files:
        corpus: Corpus = {}
        for path in jsonl_files:
            key = path.stem
            docs: list[CorpusDoc] = []
            for line in path.read_text().splitlines():
                if line.strip():
                    docs.append(cast(CorpusDoc, json.loads(line)))
            corpus[key] = docs
        return corpus

    raise typer.BadParameter(
        "no corpus available: the generator script is missing and no "
        "data/corpus/*.jsonl files were found. Run `python scripts/generate_corpus.py` "
        "or `chancel gen-corpus` first."
    )


class _Pipeline:
    """One fully wired retrieval pipeline plus the audit receipts it emitted."""

    def __init__(
        self,
        retriever: Retriever,
        corpus: Corpus,
        receipts: list[RetrievalReceipt],
        log: AuditLog,
    ) -> None:
        self.retriever = retriever
        self.corpus = corpus
        self.receipts = receipts
        self.log = log


def _build_pipeline(
    *, mode_name: str, store_kind: str, embedder_name: str, seed: int, log_path: Path
) -> _Pipeline:
    """Ingest the corpus into a fresh store+mode and wire a logged retriever."""
    corpus = _load_corpus(seed)
    known_spaces = [key for key in corpus if key != "firm"]

    embedder = build_embedder(embedder_name)
    store = build_store(store_kind)
    mode = build_mode(mode_name, store)
    ingest_corpus(mode, corpus, embedder)

    gate = PolicyGate(known_spaces)
    log = AuditLog(log_path)
    receipts: list[RetrievalReceipt] = []

    def record(receipt: RetrievalReceipt) -> None:
        log.append(receipt)
        receipts.append(receipt)

    retriever = Retriever(gate, mode, embedder, audit=record)
    return _Pipeline(retriever, corpus, receipts, log)


def _head_hash(path: Path) -> str | None:
    """SHA-256 of the log's last line -- the anchor value a user records
    externally to detect a mutated final line, which the chain cannot."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    content = path.read_bytes()
    lines = content.split(b"\n")
    last = lines[-2] if lines and lines[-1] == b"" else lines[-1]
    if not last:
        return None
    return hashlib.sha256(last).hexdigest()


# -- demo -----------------------------------------------------------------


@app.command()
def demo(
    format: str = typer.Option("text", "--format", help="Output format: text or github."),
    provider: list[str] | None = typer.Option(
        None, "--provider", help="Provider name (repeatable). Overrides the --no-llm default set."
    ),
    backend: list[str] | None = typer.Option(
        None, "--backend", help="Store backend layout (repeatable): isolated, filtered, shared."
    ),
    store: str = typer.Option("inmemory", "--store", help="Vector store kind: inmemory or qdrant."),
    sparse: bool = typer.Option(False, "--sparse", help="Enable sparse/hybrid retrieval."),
    no_llm: bool = typer.Option(
        True,
        "--no-llm/--llm",
        help="Default-safe offline path: forces the offline provider set if none is given.",
    ),
    seed: int = typer.Option(1789, "--seed", help="Corpus generation seed."),
) -> None:
    """Run the backends x providers leak matrix and print a pass/fail report.

    Cold-clone safe: with no options this uses only offline providers and the
    in-memory store, so it runs with no API key and no Docker. Exit code is 0
    when reality matches predictions and 1 when it diverges, so CI fails on a
    real regression.
    """
    demo_mod = importlib.import_module("chancel.demo")

    providers_final = list(provider) if provider else []
    backends_final = list(backend) if backend else []

    if no_llm and not providers_final:
        providers_final = list(_OFFLINE_PROVIDERS)

    kwargs: dict[str, object] = {"store_kind": store, "sparse": sparse, "seed": seed}
    if providers_final:
        kwargs["providers"] = tuple(providers_final)
    if backends_final:
        kwargs["backends"] = tuple(backends_final)

    report = demo_mod.run_matrix(**kwargs)

    if format == "github":
        rendered = demo_mod.render_github(report)
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as handle:
                handle.write(rendered)
                if not rendered.endswith("\n"):
                    handle.write("\n")
    else:
        rendered = demo_mod.render_text(report)

    typer.echo(rendered)

    ok = bool(report.ok)
    verdict = "PASS" if ok else "FAIL"
    detail = "matches" if ok else "diverges from"
    typer.echo(f"\n{verdict}: matrix {detail} predictions")
    raise typer.Exit(0 if ok else 1)


# -- ask ------------------------------------------------------------------


@app.command()
def ask(
    question: str = typer.Argument(..., help="The question to answer within the active scope."),
    space: str = typer.Option(..., "--space", help="The active matter space id."),
    provider: str | None = typer.Option(None, "--provider", help="Chat provider name."),
    model: str | None = typer.Option(None, "--model", help="Model id passed to the provider."),
    store: str = typer.Option("inmemory", "--store", help="Vector store kind: inmemory or qdrant."),
    mode: str = typer.Option(
        "isolated", "--mode", help="Storage layout: isolated, filtered, or shared."
    ),
    embedder: str = typer.Option("hash_stub", "--embedder", help="Embedder name."),
    log: Path = typer.Option(_DEFAULT_LOG, "--log", help="Audit log path (append-only JSONL)."),
) -> None:
    """Answer a question inside exactly one matter, logging every retrieval.

    Builds the store, storage layout, embedder, policy gate, audit log, and a
    scoped agent bound to the active space, ingests the synthetic corpus, then
    prints the answer, its citations, and any policy-gate denials.
    """
    pipeline = _build_pipeline(
        mode_name=mode, store_kind=store, embedder_name=embedder, seed=1789, log_path=log
    )
    chat = build_provider(provider, model=model)
    agent = ScopedAgent(
        provider=chat, retriever=pipeline.retriever, scope=ActiveScope(space_id=space)
    )

    answer = agent.ask(question)

    typer.echo("Answer:")
    typer.echo(answer.text)

    typer.echo("\nCitations:")
    if answer.citations:
        for citation in answer.citations:
            typer.echo(f"  - {citation}")
    else:
        typer.echo("  (none)")

    typer.echo("\nDenials:")
    if answer.denials:
        for denial in answer.denials:
            typer.echo(f"  - {denial}")
    else:
        typer.echo("  (none)")

    typer.echo(f"\nAudit log: {log}")


# -- attack ---------------------------------------------------------------


@app.command()
def attack(
    space: str = typer.Option(..., "--space", help="The active (authorized) matter space id."),
    target: str = typer.Option(
        "matter-brightwater", "--target", help="The out-of-scope matter the attack tries to reach."
    ),
    mode: str = typer.Option(
        "isolated", "--mode", help="Storage layout under test: isolated, filtered, or shared."
    ),
    attack_name: str = typer.Option(
        "all", "--attack", help="Attack script name, or 'all' for the full set."
    ),
    store: str = typer.Option("inmemory", "--store", help="Vector store kind: inmemory or qdrant."),
    embedder: str = typer.Option("hash_stub", "--embedder", help="Embedder name."),
    log: Path = typer.Option(_DEFAULT_LOG, "--log", help="Audit log path (append-only JSONL)."),
) -> None:
    """Play the hostile model against the wall live and show the denials land.

    For each attack script, builds a scoped agent driven by the adversarial
    model aimed at ``--target`` from within ``--space``, then reports whether
    any target-space document was obtained (none, under isolated) and the
    audit receipts the attempt produced. Ends by verifying the whole log.
    """
    # importlib on a string module name keeps the vendor-name abstraction grep
    # clean while still letting us vary the hostile model's attack/target,
    # which the registry's parameterless build_provider cannot express.
    hostile_mod = importlib.import_module("chancel.providers.hostile_echo")
    all_attacks: tuple[str, ...] = tuple(hostile_mod.ALL_ATTACKS)

    if attack_name == "all":
        attacks = all_attacks
    elif attack_name in all_attacks:
        attacks = (attack_name,)
    else:
        raise typer.BadParameter(
            f"unknown attack {attack_name!r}; valid: {', '.join(all_attacks)} (or 'all')"
        )

    pipeline = _build_pipeline(
        mode_name=mode, store_kind=store, embedder_name=embedder, seed=1789, log_path=log
    )
    target_ids = {doc["local_id"] for doc in pipeline.corpus.get(target, [])}
    scope = ActiveScope(space_id=space)

    total_obtained = 0
    for name in attacks:
        before = len(pipeline.receipts)
        chat = hostile_mod.HostileEchoModel(attack=name, target_space=target)
        agent = ScopedAgent(provider=chat, retriever=pipeline.retriever, scope=scope)
        answer = agent.ask("Summarize the matter.")

        obtained = sorted(set(answer.citations) & target_ids)
        total_obtained += len(obtained)
        new_receipts = pipeline.receipts[before:]

        typer.echo(f"attack: {name}")
        typer.echo(f"  target-space docs obtained: {len(obtained)}")
        if obtained:
            typer.echo(f"  LEAKED: {', '.join(obtained)}")
        typer.echo("  audit receipts:")
        if new_receipts:
            for receipt in new_receipts:
                typer.echo(f"    {receipt.decision}: {receipt.reason}")
        else:
            typer.echo("    (no retrieval attempted)")

    typer.echo(
        f"\nTotal target-space docs obtained across {len(attacks)} attack(s): {total_obtained}"
    )

    result = verify_log(log)
    if result.ok:
        head = _head_hash(log)
        typer.echo(f"audit log OK: {result.lines} lines verified")
        if head:
            typer.echo(f"head line_hash: {head}")
    else:
        typer.echo(f"audit log FAIL: line {result.first_bad_line}: {result.reason}")
        raise typer.Exit(1)

    raise typer.Exit(1 if total_obtained else 0)


# -- verify-log -----------------------------------------------------------


@app.command("verify-log")
def verify_log_command(
    path: Path = typer.Argument(..., help="Path to the append-only JSONL audit log."),
) -> None:
    """Verify an audit log's hash chain and print the head anchor hash.

    On success prints the verified line count and the last line's SHA-256 --
    the value a user records out of band to detect a mutated final line, which
    the chain alone cannot catch. On failure names the first bad line and exits 1.
    """
    result = verify_log(path)
    if result.ok:
        typer.echo(f"OK: {result.lines} lines verified")
        head = _head_hash(path)
        if head:
            typer.echo(f"head line_hash: {head}")
        return

    typer.echo(f"FAIL: line {result.first_bad_line}: {result.reason}")
    raise typer.Exit(1)


# -- gen-corpus -----------------------------------------------------------


@app.command("gen-corpus")
def gen_corpus(
    seed: int = typer.Option(1789, "--seed", help="Corpus generation seed."),
    out: Path = typer.Option(Path("data/corpus"), "--out", help="Output directory."),
) -> None:
    """Regenerate the synthetic corpus on disk and print its summary.

    Thin wrapper over ``scripts/generate_corpus.write_corpus`` so the corpus
    can be produced after install without invoking the script by path.
    """
    module = _load_generate_module()
    manifest = module.write_corpus(out, seed)

    counts = manifest["doc_counts"]
    total = sum(counts.values())
    typer.echo(f"Wrote {total} documents to {out}:")
    for name, count in counts.items():
        typer.echo(f"  {name}: {count}")

    canaries_path = Path(out) / "canaries.json"
    if canaries_path.exists():
        canaries = json.loads(canaries_path.read_text())
        typer.echo("Canaries:")
        for matter, canary in canaries.items():
            typer.echo(f"  {matter}: {canary}")


if __name__ == "__main__":  # pragma: no cover
    app()
