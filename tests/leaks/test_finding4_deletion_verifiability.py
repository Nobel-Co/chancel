"""Finding 4 -- deletion verifiability.

The finding is NOT about whether rows are gone (they may well be gone under
every backend). It is about whether the *check* that certifies deletion is
independent of the mechanism under test.

isolated: delete drops the collection; verify via list_collections(), which is
external to the query path entirely -- no query runs, so no query-path bug
could fake the result. ``independent_of_query_path`` is True -> clean.

filtered: delete filters rows out of the shared 'corpus' collection; the only
available verification re-runs the same filter+query path search() uses. It
cannot independently certify deletion: to believe "gone", you must already
trust the filter that is the thing in question. ``independent_of_query_path``
is False -> RED, asserted on the independence property, not on row counts.
"""

from __future__ import annotations

import pytest
from _probes import SCOPE_SPACE, TARGET_SPACE, build_stack

from chancel.model import space_collection


def test_isolated_deletion_is_verifiable_out_of_band() -> None:
    stack = build_stack("isolated")
    target_collection = space_collection(TARGET_SPACE)
    assert target_collection in stack.store.list_collections()

    delete_report = stack.mode.delete_space(TARGET_SPACE)
    verify_report = stack.mode.verify_deletion(TARGET_SPACE)

    # The out-of-band check: the collection is simply not there any more.
    assert target_collection not in stack.store.list_collections()
    assert delete_report.independent_of_query_path is True
    assert verify_report.independent_of_query_path is True
    assert verify_report.method == "list_collections"
    assert verify_report.deleted is True


def test_filtered_deletion_cannot_be_certified_independently() -> None:
    """RED on the independence property.

    Note we do NOT assert rows survive -- delete_by_space really removes them.
    The finding is that the verification re-uses the mechanism under test, so it
    proves nothing a filter bug couldn't also fake.
    """
    stack = build_stack("filtered")

    delete_report = stack.mode.delete_space(TARGET_SPACE)
    verify_report = stack.mode.verify_deletion(TARGET_SPACE)

    assert verify_report.independent_of_query_path is False, (
        "EXPECTED-RED REGRESSION: filtered verify_deletion claimed independence. "
        "Its only check (stores/filtered.py verify_deletion) re-runs the same "
        "store.query + filter_logical path search() uses; it CANNOT certify "
        "deletion without trusting the mechanism under test (finding 4). If this "
        "flipped to True, the check stopped re-using the filter and the finding "
        "is no longer measured."
    )
    assert delete_report.independent_of_query_path is False
    assert verify_report.method == "filtered_query"


def test_shared_deletion_also_lacks_an_independent_check() -> None:
    stack = build_stack("shared")
    stack.mode.delete_space(SCOPE_SPACE)
    verify_report = stack.mode.verify_deletion(SCOPE_SPACE)
    assert verify_report.independent_of_query_path is False
    assert verify_report.method == "filtered_query"


@pytest.mark.parametrize("backend", ["isolated", "filtered", "shared"])
def test_independence_property_matches_backend(backend: str) -> None:
    # Pinned truth table: only the collection-per-space layout can certify.
    expected = {"isolated": True, "filtered": False, "shared": False}[backend]
    stack = build_stack(backend)
    stack.mode.delete_space(TARGET_SPACE)
    assert stack.mode.verify_deletion(TARGET_SPACE).independent_of_query_path is expected
