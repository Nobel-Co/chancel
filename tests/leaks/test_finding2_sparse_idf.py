"""Finding 2 -- the sparse-vector IDF side channel.

This is the subtle finding: even when the *returned points* are correctly
isolated by a payload filter, the *ranking statistics* are not. Under a shared
shard (``filtered`` mode) the inverse-document-frequency corpus blends every
tenant's vocabulary, so one matter's corpus growing measurably shifts another
matter's scores -- a covert channel that needs no document to cross at all.

The load-bearing vendor citation (PRPs/ai_docs/qdrant-multitenancy.md,
"Per-tenant IDF statistics", verbatim):

    "By default, these statistics are computed across the entire shard being
    queried. When using payload-filter-based multitenancy, this blends every
    tenant's vocabulary into one set of statistics, so a term's IDF no longer
    reflects its rarity within a specific tenant's data."

    "The `idf` search parameter lets you correct this by narrowing the
    population -- the IDF corpus -- that Qdrant computes statistics over."

Under ``isolated`` the statistics cannot cross because the collections do not
share a shard; under ``filtered`` they cross unless every caller remembers the
`idf` parameter on every query. The existence of that escape hatch is the
finding.

WHICH PATH RAN: the qdrant + fastembed(BM25) reproduction is SKIPPED-with-
reason whenever fastembed is not installed (it is not, in this environment,
and the chancel qdrant adapter also only ranks dense vectors -- see
stores/qdrant.py `del sparse`). The ASSERTING reproduction is the offline
manual-IDF path below: it computes textbook BM25 over the real corpus using
the hash_stub sparse vectors as term-frequency maps, choosing the IDF
population to model shard-wide (filtered) vs per-tenant (isolated) statistics.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _probes import (
    SCOPE_SPACE,
    TARGET_SPACE,
    bm25_score,
    padded_matter_docs,
    term_frequencies,
)
from generate_corpus import generate

# A fixed query in brightwater's vocabulary, and a fixed brightwater document
# (the Settlement Posture memo -- it carries brightwater's canary and the
# seaworthiness/salvage terms the query uses).
_FIXED_QUERY = "seaworthiness salvage award policy limit hull underwriter"
_SCORE_EPSILON = 1e-6
_PAD_COUNT = 40


def _fixed_target_doc(corpus: dict[str, list[dict[str, str | None]]]) -> dict[str, str | None]:
    for doc in corpus[TARGET_SPACE]:
        if doc["local_id"] == "b8":
            return doc
    raise AssertionError("expected brightwater doc b8 in corpus")


def test_filtered_idf_is_a_side_channel_isolated_is_not(tmp_path: Path) -> None:
    """filtered: padding the OTHER matter shifts this matter's score (RED).
    isolated: the same padding changes nothing (clean)."""
    base = generate(1789)
    firm = base["firm"]
    alderman = base[SCOPE_SPACE]
    brightwater = base[TARGET_SPACE]

    query_tf = term_frequencies(_FIXED_QUERY)
    target_tf = term_frequencies(_fixed_target_doc(base)["text"] or "")

    def score(population_docs: list[dict[str, str | None]]) -> float:
        population = [term_frequencies(d["text"] or "") for d in population_docs]
        return bm25_score(query_tf, target_tf, population)

    # BEFORE padding.
    # filtered: IDF population is the whole shared shard (firm + both matters).
    # isolated: IDF population is brightwater's own collection only.
    filtered_before = score(firm + alderman + brightwater)
    isolated_before = score(brightwater)

    # Grow the OTHER tenant (alderman) via the real generator's padding.
    alderman_padded = padded_matter_docs(tmp_path, SCOPE_SPACE, _PAD_COUNT)
    assert len(alderman_padded) == len(alderman) + _PAD_COUNT

    filtered_after = score(firm + alderman_padded + brightwater)
    isolated_after = score(brightwater)

    filtered_delta = abs(filtered_after - filtered_before)
    isolated_delta = abs(isolated_after - isolated_before)

    # RED: the shared-shard score of a brightwater doc moved because alderman's
    # corpus grew -- brightwater's ranking now depends on a matter it can't see.
    assert filtered_delta > _SCORE_EPSILON, (
        "EXPECTED-RED REGRESSION: filtered-mode IDF did NOT shift when the other "
        "tenant grew. The side channel of finding 2 stopped reproducing -- the "
        "shard-wide IDF population is what makes filtered leakable here."
    )
    # CLEAN: the per-collection score is invariant to the other tenant entirely.
    assert isolated_delta == pytest.approx(0.0, abs=_SCORE_EPSILON), (
        "isolated-mode score must not move when another collection grows; the "
        "collections do not share a shard, so IDF statistics cannot cross."
    )

    # Report the exact numbers for the human reading the run.
    print(
        "\n[finding2 offline manual-IDF] "
        f"filtered: {filtered_before:.6f} -> {filtered_after:.6f} "
        f"(delta {filtered_delta:.6f}); "
        f"isolated: {isolated_before:.6f} -> {isolated_after:.6f} "
        f"(delta {isolated_delta:.6f}); pad={_PAD_COUNT} docs into {SCOPE_SPACE}"
    )


def test_qdrant_fastembed_bm25_variant_reason_if_skipped() -> None:
    """The real qdrant+BM25 reproduction, skipped-with-reason when unavailable.

    NEVER silently passes: this test either exercises a real sparse-IDF query
    against qdrant, or skips naming why. In this environment fastembed is not
    installed and, independently, chancel's qdrant adapter ranks dense vectors
    only (stores/qdrant.py `del sparse`), so the asserting reproduction is the
    offline manual-IDF test above.
    """
    pytest.importorskip(
        "fastembed",
        reason=(
            "fastembed (qdrant/bm25) not installed; sparse-IDF-over-real-qdrant "
            "cannot run. Offline manual-IDF reproduction in "
            "test_filtered_idf_is_a_side_channel_isolated_is_not is the asserting path."
        ),
    )
    pytest.importorskip(
        "qdrant_client",
        reason="qdrant-client not installed; install with `uv sync --extra qdrant`.",
    )
    # If both are ever present, this is where a real sparse-vector query with
    # and without the `idf` search-parameter scoping would be asserted. Left as
    # a skip-gated stub so the suite never claims to have run it when it did not.
    pytest.skip(
        "chancel's qdrant adapter ranks dense vectors only (stores/qdrant.py "
        "`del sparse`); a sparse BM25/IDF query path is not wired, so the "
        "reproduction is the offline manual-IDF test."
    )
