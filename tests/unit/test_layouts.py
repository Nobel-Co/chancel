"""Leak-suite-adjacent unit tests: gate-authorized search per layout.

isolated and filtered must return only own-space + firm docs; shared is
DELIBERATELY weak and must be able to return the other matter's docs for a
query aimed at that matter's vocabulary -- that is finding 1 of the leak
suite, and the assertion below is pinned so nobody "fixes" shared.py by
accident.
"""

from __future__ import annotations

from typing import Any

import pytest
from generate_corpus import generate

from chancel.embedders.hash_stub import HashStubEmbedder
from chancel.ingest import ingest_corpus
from chancel.model import ActiveScope
from chancel.policy import PolicyGate
from chancel.stores.base import StorageMode
from chancel.stores.filtered import FilteredStore
from chancel.stores.inmemory import InMemoryStore
from chancel.stores.isolated import IsolatedStore
from chancel.stores.shared import SharedStore

CORPUS = generate()
SPACE_IDS = ["matter-alderman", "matter-brightwater"]


def _build(mode_cls: type[Any]) -> tuple[StorageMode, HashStubEmbedder]:
    store = InMemoryStore()
    embedder = HashStubEmbedder()
    mode = mode_cls(store)
    ingest_corpus(mode, CORPUS, embedder)
    return mode, embedder


@pytest.mark.parametrize("mode_cls", [IsolatedStore, FilteredStore])
def test_own_space_search_never_returns_other_matter(mode_cls: type[Any]) -> None:
    mode, embedder = _build(mode_cls)
    gate = PolicyGate(SPACE_IDS)
    scope = ActiveScope(space_id="matter-alderman")
    authorized = gate.authorize(scope, gate.default_allowlist(scope))

    dense = embedder.embed_dense(["seaworthiness salvage subrogation underwriter"])[0]
    results = mode.search(authorized, dense, None, limit=20)

    assert results, "expected at least one hit"
    for chunk in results:
        assert chunk.doc_id.space_id in (None, "matter-alderman")


def test_shared_mode_can_leak_other_matter_content_by_design() -> None:
    mode, embedder = _build(SharedStore)
    gate = PolicyGate(SPACE_IDS)
    scope = ActiveScope(space_id="matter-alderman")
    authorized = gate.authorize(scope, gate.default_allowlist(scope))

    # Brightwater-specific vocabulary; no alderman document uses these terms.
    dense = embedder.embed_dense(["seaworthiness salvage subrogation underwriter"])[0]
    results = mode.search(authorized, dense, None, limit=20)

    # DELIBERATE WEAKNESS, pinned: shared passes no filter at all, so
    # brightwater content surfaces even though `authorized` names only firm
    # + matter-alderman. This is finding 1 of the leak suite and must stay
    # red -- do not "fix" it by adding a filter to shared.py.
    assert any(chunk.doc_id.space_id == "matter-brightwater" for chunk in results)


@pytest.mark.parametrize(
    ("mode_cls", "independent"),
    [(IsolatedStore, True), (FilteredStore, False), (SharedStore, False)],
)
def test_delete_and_verify_deletion_fields(mode_cls: type[Any], independent: bool) -> None:
    mode, _ = _build(mode_cls)

    delete_report = mode.delete_space("matter-alderman")
    assert delete_report.space_id == "matter-alderman"
    assert delete_report.deleted is True

    verify_report = mode.verify_deletion("matter-alderman")
    assert verify_report.space_id == "matter-alderman"
    assert verify_report.deleted is True
    assert verify_report.independent_of_query_path is independent
