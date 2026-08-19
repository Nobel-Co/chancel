"""The one place tests/conformance/ names an adapter by string.

PRP-12's success criterion is: "Adding a provider = implement one protocol +
pass tests/conformance/." A conformance suite that has to be *edited* to
accommodate a new adapter would fail that criterion even if the new adapter
passed every test -- the point is that the suite itself never changes shape.

This module is the deliberate, narrow exception: something has to enumerate
which adapters exist so ``pytest.mark.parametrize`` has names to iterate.
Putting that enumeration in exactly one file, as plain lists, means adding an
adapter is:

1. Implement the protocol (``ChatModel`` / ``Embedder`` / ``VectorStore`` /
   ``StorageMode``).
2. Add its name to the relevant list below.

Nothing else in ``tests/conformance/`` changes -- no new test function, no
new assertion, no edited parametrize decorator. ``test_new_adapter_is_drop_in.py``
is the proof: it runs a brand-new adapter that is defined entirely outside
this repo's registry and is *not* named anywhere in this file, through the
exact same assertion helpers (``tests/conformance/_contracts.py``) that the
suites parametrized off these lists use, and it passes with zero edits to
either this file or the test bodies.

Why this can't just be read off ``chancel.registry``: ``registry.py``
exposes ``build_*`` constructors but no listing API (by design -- it is a
name-to-constructor dispatch table, not an adapter catalog), and this
worktree's mandate is read-only on ``src/``. So this file -- not a hardcoded
list buried in each test body -- is the single source of truth the suite
enumerates from. Keep the names here in sync with ``chancel.registry``'s
``_PROVIDER_NAMES`` / ``_EMBEDDER_NAMES`` / ``_STORE_KINDS`` / ``_MODE_NAMES``
by hand; a mismatch is a bug in this file, not in the suite's structure.
"""

from __future__ import annotations

# ChatModel adapters. Offline: no network, no API key, run in every tier.
PROVIDERS_OFFLINE = ["echo", "hostile_echo"]
# All registered ChatModel adapters, offline + the two live-API adapters.
# anthropic/openai_compat are driven through tests/cassettes/ via
# httpx.MockTransport / httpx2.MockTransport -- see test_chatmodel_conformance.py
# -- so "live" here means "has a real SDK dependency", not "makes a network call".
PROVIDERS_ALL = [*PROVIDERS_OFFLINE, "anthropic", "openai_compat"]

# Embedder adapters. Offline: stdlib-only, no download, no API key.
EMBEDDERS_OFFLINE = ["hash_stub"]
# Optional Embedder adapters: importorskip'd on their dependency.
# fastembed_local downloads model weights on first use (skipped here if the
# fastembed package itself isn't installed); openai_compat is driven through
# a mocked httpx2 transport, same rationale as the chat-model adapters above.
EMBEDDERS_OPTIONAL = ["fastembed_local", "openai_compat"]

# VectorStore adapters. qdrant is importorskip'd on qdrant-client and uses a
# per-test tmp_path (local-mode Qdrant holds a filesystem lock per path).
STORES = ["inmemory", "qdrant"]

# StorageMode layouts.
MODES = ["isolated", "filtered", "shared"]
