"""Proof of the drop-in criterion.

PRP-12's success criterion: "Adding a provider = implement one protocol +
pass tests/conformance/." ``NullEmbedder`` and ``ConstantChatModel`` below
are defined entirely in this file. They are not registered in
``chancel.registry``, not imported by any other test, and not named
anywhere in ``registry_conformance.py`` -- a brand-new adapter, exactly as a
forker would write one.

They are run through the *exact same* assertion helpers
(``tests/conformance/_contracts.py``) that ``test_chatmodel_conformance.py``
and ``test_embedder_conformance.py`` parametrize across the registered
adapters with. Nothing in this file, or in any other file under
``tests/conformance/``, was edited to accommodate these two classes.

That is the proof: a new adapter that requires editing this suite is a
design failure, not a test failure. This test demonstrates the converse
holds -- a conforming adapter passes with zero edits to the suite, only the
addition of the adapter itself.
"""

from __future__ import annotations

from collections.abc import Sequence

from _contracts import (
    assert_chatmodel_shape,
    assert_complete_contract,
    assert_dense_shape,
    assert_deterministic_dense,
    assert_idempotent,
    assert_sparse_contract,
    assert_tool_calls_well_formed,
)

from chancel.providers.base import ChatTurn, ModelReply, ToolSpec
from chancel.stores.base import SparseVector


class NullEmbedder:
    """A tiny ``Embedder``, defined only in this file: ``dense_dim`` 8,
    deterministic near-zero vectors keyed off text length, no sparse
    support. Never registered in ``chancel.registry``."""

    dense_dim: int = 8

    def embed_dense(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        vectors: list[tuple[float, ...]] = []
        for text in texts:
            seed = (len(text) % 7) * 0.01
            vectors.append(tuple(seed + 0.0001 * i for i in range(self.dense_dim)))
        return vectors

    def embed_sparse(self, texts: Sequence[str]) -> list[SparseVector] | None:
        del texts
        return None


class ConstantChatModel:
    """A tiny ``ChatModel``, defined only in this file: always answers with
    fixed text, never calls a tool. Never registered in
    ``chancel.registry``."""

    name: str = "conformance_probe"

    def complete(
        self, system: str, turns: Sequence[ChatTurn], tools: Sequence[ToolSpec]
    ) -> ModelReply:
        del system, turns, tools
        return ModelReply(text="a fixed, constant answer", tool_calls=())


_TOOL = ToolSpec(
    name="search_matter_context",
    description="search the current matter",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    },
)


def test_null_embedder_passes_the_shared_embedder_conformance_helpers() -> None:
    embedder = NullEmbedder()
    assert_dense_shape(embedder, ["one text", "a longer piece of text"])
    assert_deterministic_dense(embedder, "one text")
    assert_sparse_contract(embedder, ["one text", "a longer piece of text"])


def test_constant_chatmodel_passes_the_shared_chatmodel_conformance_helpers() -> None:
    model = ConstantChatModel()
    assert_chatmodel_shape(model)

    turns = [ChatTurn(role="user", text="hello")]
    reply = assert_complete_contract(model, "system prompt", turns, [_TOOL])
    assert_tool_calls_well_formed(reply, {_TOOL.name})
    assert_idempotent(model, "system prompt", turns, [_TOOL])
