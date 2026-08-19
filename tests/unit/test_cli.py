"""Unit tests for the ``chancel`` CLI (chancel.cli:app).

The ``demo`` command is covered behind ``pytest.importorskip("chancel.demo")``
because the demo module is built concurrently and may land after this suite.
Everything else exercises the offline, cold-clone path: echo / hostile_echo
providers, the in-memory store, the hash-stub embedder.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from chancel.cli import app

runner = CliRunner()

_VENDOR_NAMES = re.compile(r"anthropic|openai|groq|ollama", re.IGNORECASE)


# -- demo -----------------------------------------------------------------


def test_demo_no_llm_exits_zero_and_reports_backends_and_pass() -> None:
    pytest.importorskip("chancel.demo")
    result = runner.invoke(app, ["demo", "--no-llm"])
    assert result.exit_code == 0, result.output
    assert "isolated" in result.output
    assert "filtered" in result.output
    assert "shared" in result.output
    assert "PASS" in result.output


def test_demo_github_format_is_markdown_table_and_writes_step_summary(tmp_path: Path) -> None:
    pytest.importorskip("chancel.demo")
    summary = tmp_path / "step-summary.md"

    result = runner.invoke(
        app,
        ["demo", "--no-llm", "--format", "github"],
        env={"GITHUB_STEP_SUMMARY": str(summary)},
    )
    assert result.exit_code == 0, result.output
    assert "|" in result.output  # markdown table pipes
    assert summary.exists()
    assert "|" in summary.read_text()


# -- ask ------------------------------------------------------------------


def test_ask_prints_answer_and_citation_and_writes_verifiable_log(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    result = runner.invoke(
        app,
        [
            "ask",
            "summarize the matter",
            "--space",
            "matter-alderman",
            "--mode",
            "isolated",
            "--store",
            "inmemory",
            "--log",
            str(log),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Answer:" in result.output
    assert "Citations:" in result.output
    # At least one citation line was printed.
    assert re.search(r"Citations:\n\s+- \S+", result.output), result.output
    assert log.exists()

    verify = runner.invoke(app, ["verify-log", str(log)])
    assert verify.exit_code == 0, verify.output
    assert "OK:" in verify.output


# -- attack ---------------------------------------------------------------


def test_attack_reports_zero_target_docs_and_verifies_log(tmp_path: Path) -> None:
    log = tmp_path / "attack.jsonl"
    result = runner.invoke(
        app,
        [
            "attack",
            "--space",
            "matter-alderman",
            "--target",
            "matter-brightwater",
            "--mode",
            "isolated",
            "--log",
            str(log),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "target-space docs obtained: 0" in result.output
    assert "Total target-space docs obtained" in result.output
    assert "audit log OK" in result.output
    assert log.exists()

    # The whole chain the attack produced verifies independently.
    verify = runner.invoke(app, ["verify-log", str(log)])
    assert verify.exit_code == 0, verify.output


# -- verify-log -----------------------------------------------------------


def test_verify_log_good_then_tampered(tmp_path: Path) -> None:
    log = tmp_path / "audit.jsonl"
    ask = runner.invoke(
        app,
        ["ask", "damages", "--space", "matter-alderman", "--log", str(log)],
    )
    assert ask.exit_code == 0, ask.output

    good = runner.invoke(app, ["verify-log", str(log)])
    assert good.exit_code == 0, good.output
    assert "OK:" in good.output
    assert "head line_hash:" in good.output

    # Tamper: append a line that is not a valid receipt.
    line_count = len(log.read_text().splitlines())
    with open(log, "a", encoding="utf-8") as handle:
        handle.write("this is not json\n")

    bad = runner.invoke(app, ["verify-log", str(log)])
    assert bad.exit_code == 1, bad.output
    assert "FAIL" in bad.output
    assert str(line_count + 1) in bad.output


# -- gen-corpus -----------------------------------------------------------


def test_gen_corpus_writes_files_and_prints_canary_summary(tmp_path: Path) -> None:
    out = tmp_path / "corpus"
    result = runner.invoke(app, ["gen-corpus", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "firm.jsonl").exists()
    assert (out / "matter-alderman.jsonl").exists()
    assert (out / "matter-brightwater.jsonl").exists()
    assert "CANARY-" in result.output


# -- abstraction boundary -------------------------------------------------


def test_cli_module_names_no_vendor_providers() -> None:
    source = Path(__file__).resolve().parents[2] / "src" / "chancel" / "cli.py"
    assert not _VENDOR_NAMES.search(source.read_text()), (
        "cli.py must not name a concrete vendor provider (abstraction grep)"
    )
