"""The agent loop: neutral all the way down.

``ScopedAgent`` never asks which provider it is talking to and never sees a
collection name. The active scope is bound once, at construction, to a
single tool with a single string parameter, ``query``. The retriever
validates every call's arguments before anything reaches ``PolicyGate``, so
a model (or an injection in retrieved text) asking for "other matters" has
no parameter through which the ask can travel -- there is nothing to smuggle
a collection name, a space id, or a filter into.

The system prompt below tells the model to answer only from the current
matter and firm playbooks. That sentence is deliberately **not** the
enforcement -- it is exactly the kind of instruction the ``shared`` storage
layout relies on and the leak suite shows failing. The wall is
``retriever.retrieve()`` calling ``PolicyGate.authorize()``, which runs
whether or not the model reads the prompt, honors it, or exists at all.
"""

from __future__ import annotations

from pydantic import BaseModel

from chancel.exceptions import ScopeViolation
from chancel.model import ActiveScope
from chancel.providers.base import ChatModel, ChatTurn, ToolCall, ToolResult, ToolSpec
from chancel.retriever import Retriever

TOOL_NAME = "search_matter_context"

_SEARCH_TOOL = ToolSpec(
    name=TOOL_NAME,
    description=(
        "Search the firm playbooks and THE CURRENT MATTER ONLY for context "
        "relevant to a question. Takes a single free-text query. The matter "
        "searched is fixed for this conversation and cannot be chosen or "
        "changed by this call."
    ),
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    },
)

_SYSTEM_PROMPT_TEMPLATE = (
    "You are a firm assistant helping with legal work on one matter. "
    "Only ever answer from the current matter and firm playbooks. "
    "Use the {tool_name} tool to find supporting context before answering."
)


class AgentAnswer(BaseModel, frozen=True):
    """The result of one ``ScopedAgent.ask()`` call."""

    text: str
    citations: tuple[str, ...]
    denials: tuple[str, ...]
    rounds: int


class ScopedAgent:
    """Binds one ``ActiveScope`` at construction; the model never supplies one.

    See module docstring for why the tool signature -- not the system
    prompt -- is the enforcement boundary.
    """

    def __init__(
        self,
        *,
        provider: ChatModel,
        retriever: Retriever,
        scope: ActiveScope,
        system_extra: str = "",
        max_rounds: int = 4,
    ) -> None:
        self._provider = provider
        self._retriever = retriever
        self._scope = scope
        self._max_rounds = max_rounds
        system = _SYSTEM_PROMPT_TEMPLATE.format(tool_name=TOOL_NAME)
        self._system = f"{system} {system_extra}" if system_extra else system

    def ask(self, question: str) -> AgentAnswer:
        turns: list[ChatTurn] = [ChatTurn(role="user", text=question)]
        citations: list[str] = []
        denials: list[str] = []
        rounds = 0
        last_text = ""

        for _ in range(self._max_rounds):
            rounds += 1
            reply = self._provider.complete(self._system, turns, (_SEARCH_TOOL,))
            last_text = reply.text

            if not reply.tool_calls:
                break

            turns.append(ChatTurn(role="assistant", text=reply.text, tool_calls=reply.tool_calls))

            results: list[ToolResult] = []
            for call in reply.tool_calls:
                result, new_citations, denial = self._execute(call)
                results.append(result)
                citations.extend(new_citations)
                if denial is not None:
                    denials.append(denial)
            turns.append(ChatTurn(role="tool_result", tool_results=tuple(results)))

        return AgentAnswer(
            text=last_text,
            citations=tuple(citations),
            denials=tuple(denials),
            rounds=rounds,
        )

    def _execute(self, call: ToolCall) -> tuple[ToolResult, list[str], str | None]:
        """Validate, then (only if valid) retrieve.

        Anything other than exactly ``{"query": <str>}`` -- missing,
        wrong-typed, extra keys, or the ``__malformed__`` marker a provider
        adapter produces for unparseable arguments -- is an error result
        with NO retrieval attempted. A ``ScopeViolation`` from the gate is
        also an error result; the retriever already wrote the deny receipt,
        so this method does not log it again, only surfaces the reason.
        """
        if call.name != TOOL_NAME:
            return (
                ToolResult(call_id=call.id, content=f"unknown tool {call.name!r}", is_error=True),
                [],
                None,
            )

        query = call.arguments.get("query")
        if set(call.arguments) != {"query"} or not isinstance(query, str):
            return (
                ToolResult(
                    call_id=call.id,
                    content='invalid arguments; expected {"query": string}',
                    is_error=True,
                ),
                [],
                None,
            )

        try:
            chunks = self._retriever.retrieve(self._scope, query)
        except ScopeViolation as exc:
            return (
                ToolResult(
                    call_id=call.id,
                    content=f"denied by policy gate: {exc.reason}",
                    is_error=True,
                ),
                [],
                exc.reason,
            )

        # "\n\n" is the passage separator the echo adapter's contract
        # depends on (chancel.providers.echo) -- a real provider just reads
        # this as opaque text for the model.
        content = "\n\n".join(chunk.text for chunk in chunks)
        new_citations = [chunk.doc_id.local_id for chunk in chunks]
        return ToolResult(call_id=call.id, content=content, is_error=False), new_citations, None
