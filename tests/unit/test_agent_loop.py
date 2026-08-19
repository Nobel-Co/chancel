"""Unit tests for ScopedAgent -- the neutral loop above the adapter boundary.

Uses the echo provider plus an in-memory isolated stack over the generated
corpus (``conftest.py`` makes ``scripts/`` importable so ``generate_corpus``
can be imported directly, same as the retriever/policy unit tests).
"""

from __future__ import annotations

from collections.abc import Sequence

from generate_corpus import generate

from chancel.agent import ScopedAgent
from chancel.embedders.hash_stub import HashStubEmbedder
from chancel.ingest import ingest_corpus
from chancel.model import ActiveScope
from chancel.policy import PolicyGate
from chancel.providers.base import ChatTurn, ModelReply, ToolCall, ToolSpec
from chancel.providers.echo import EchoModel
from chancel.retriever import Retriever
from chancel.stores.inmemory import InMemoryStore
from chancel.stores.isolated import IsolatedStore

_KNOWN_SPACES = ("matter-alderman", "matter-brightwater")


def _build_stack(known_spaces: tuple[str, ...]) -> tuple[Retriever, dict]:
    corpus = generate()
    store = InMemoryStore()
    mode = IsolatedStore(store)
    embedder = HashStubEmbedder()
    ingest_corpus(mode, corpus, embedder)
    gate = PolicyGate(known_spaces)
    return Retriever(gate, mode, embedder), corpus


def test_ask_retrieves_and_answers_with_citations_from_own_matter_only() -> None:
    retriever, corpus = _build_stack(_KNOWN_SPACES)
    scope = ActiveScope(space_id="matter-alderman")
    agent = ScopedAgent(provider=EchoModel(), retriever=retriever, scope=scope)

    answer = agent.ask("contamination damages")

    assert answer.rounds == 2
    assert answer.denials == ()
    assert len(answer.citations) > 0
    assert answer.text.startswith("Echo answer based on")

    firm_ids = {doc["local_id"] for doc in corpus["firm"]}
    alderman_ids = {doc["local_id"] for doc in corpus["matter-alderman"]}
    brightwater_ids = {doc["local_id"] for doc in corpus["matter-brightwater"]}

    assert brightwater_ids.isdisjoint(answer.citations)
    assert set(answer.citations) <= (firm_ids | alderman_ids)


class _SpyRetriever:
    """Wraps a real Retriever and records every retrieve() call it sees."""

    def __init__(self, inner: Retriever) -> None:
        self._inner = inner
        self.calls: list[tuple[ActiveScope, str]] = []

    def retrieve(self, scope: ActiveScope, query: str, *, limit: int = 6):  # type: ignore[no-untyped-def]
        self.calls.append((scope, query))
        return self._inner.retrieve(scope, query, limit=limit)


class _ExtraKeyProvider:
    """Scripted fake ChatModel: first round asks for the sanctioned tool but
    smuggles an extra 'collection' key into the arguments, trying to name a
    different matter's collection directly. Second round finalizes."""

    name = "fake-extra-key"

    def complete(
        self, system: str, turns: Sequence[ChatTurn], tools: Sequence[ToolSpec]
    ) -> ModelReply:
        has_tool_result = any(turn.role == "tool_result" for turn in turns)
        if has_tool_result:
            return ModelReply(text="done", tool_calls=())
        return ModelReply(
            text="",
            tool_calls=(
                ToolCall(
                    id="c1",
                    name=tools[0].name,
                    arguments={"query": "x", "collection": "space-matter-brightwater"},
                ),
            ),
        )


def test_extra_key_argument_is_rejected_without_retrieval() -> None:
    # The retrieval tool's signature is {"query": string} only -- a
    # 'collection' key cannot be expressed by a valid call, so this must be
    # rejected as invalid arguments before the retriever (and therefore the
    # gate) ever sees it.
    retriever, _ = _build_stack(_KNOWN_SPACES)
    spy = _SpyRetriever(retriever)
    scope = ActiveScope(space_id="matter-alderman")
    agent = ScopedAgent(provider=_ExtraKeyProvider(), retriever=spy, scope=scope)  # type: ignore[arg-type]

    answer = agent.ask("anything")

    assert spy.calls == []
    assert answer.rounds == 2
    assert answer.text == "done"
    assert answer.citations == ()


class _AlwaysToolCallProvider:
    """Scripted fake ChatModel that never stops requesting the tool."""

    name = "fake-always-call"

    def complete(
        self, system: str, turns: Sequence[ChatTurn], tools: Sequence[ToolSpec]
    ) -> ModelReply:
        return ModelReply(
            text="",
            tool_calls=(ToolCall(id="c1", name=tools[0].name, arguments={"query": "x"}),),
        )


def test_max_rounds_is_respected() -> None:
    retriever, _ = _build_stack(("matter-alderman",))
    scope = ActiveScope(space_id="matter-alderman")
    agent = ScopedAgent(
        provider=_AlwaysToolCallProvider(), retriever=retriever, scope=scope, max_rounds=3
    )

    answer = agent.ask("anything")

    assert answer.rounds == 3


def test_denial_path_populates_denials_and_still_returns_an_answer() -> None:
    # The gate's known_spaces excludes the scope's own space, so every
    # retrieve() call is denied -- but ask() must still return an
    # AgentAnswer rather than propagating the ScopeViolation.
    corpus = generate()
    store = InMemoryStore()
    mode = IsolatedStore(store)
    embedder = HashStubEmbedder()
    ingest_corpus(mode, corpus, embedder)
    gate = PolicyGate(("matter-brightwater",))  # matter-alderman is NOT known
    retriever = Retriever(gate, mode, embedder)
    scope = ActiveScope(space_id="matter-alderman")
    agent = ScopedAgent(provider=EchoModel(), retriever=retriever, scope=scope)

    answer = agent.ask("contamination damages")

    assert len(answer.denials) == 1
    assert answer.denials[0] == "unknown space"
    assert answer.citations == ()
