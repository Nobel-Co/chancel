"""End-to-end: the demo a forker runs is actually green.

"Green" here means every backend behaved as PREDICTED -- including the reds
being red. ``report.ok`` is True when ``shared`` leaked-as-expected and
``filtered`` failed findings 3-4 as expected. A ✗ (ok False) is the alarm:
reality diverged from the PRP's prediction.

Runs cold-clone: no API key, no Docker (inmemory store), no downloads
(hash_stub embedder).
"""

from __future__ import annotations

from chancel.demo import (
    MatrixReport,
    render_github,
    render_text,
    run_matrix,
)


def test_run_matrix_is_green_meaning_every_prediction_held() -> None:
    report = run_matrix()
    assert isinstance(report, MatrixReport)
    assert report.ok, "\n" + render_text(report)

    # Every cell's outcome matched its expected color.
    for r in report.results:
        assert r.passed
        assert r.outcome == r.expected


def test_matrix_covers_all_three_backends() -> None:
    report = run_matrix()
    by_backend = report.by_backend()
    assert set(by_backend) == {"isolated", "filtered", "shared"}
    for backend in ("isolated", "filtered", "shared"):
        assert by_backend[backend], f"no results for backend {backend}"


def test_shared_leaks_and_filtered_fails_the_right_findings() -> None:
    report = run_matrix()
    by_finding = {(r.finding, r.backend, r.provider): r for r in report.results}

    # shared leaks the canary (finding 1), by design and predicted.
    shared_echo = by_finding[("canary-leak", "shared", "echo")]
    assert shared_echo.expected == "leaked" and shared_echo.outcome == "leaked"

    # filtered stays clean on canary content but red on findings 3 and 4.
    assert by_finding[("canary-leak", "filtered", "echo")].outcome == "clean"
    assert by_finding[("unrepresentable-call", "filtered", "n/a")].outcome == "leaked"
    assert by_finding[("deletion-verifiability", "filtered", "n/a")].outcome == "leaked"

    # isolated is clean everywhere.
    assert by_finding[("canary-leak", "isolated", "echo")].outcome == "clean"
    assert by_finding[("unrepresentable-call", "isolated", "n/a")].outcome == "denied"
    assert by_finding[("deletion-verifiability", "isolated", "n/a")].outcome == "clean"


def test_render_text_produces_a_table_with_backends_and_a_verdict() -> None:
    text = render_text(run_matrix())
    assert text
    for token in ("isolated", "filtered", "shared", "expected", "actual"):
        assert token in text
    assert "PASS" in text or "FAIL" in text


def test_render_github_produces_a_markdown_table() -> None:
    md = render_github(run_matrix())
    assert md
    assert "| finding |" in md
    for token in ("isolated", "filtered", "shared"):
        assert token in md
    assert "PASS" in md or "FAIL" in md
