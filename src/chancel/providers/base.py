"""Neutral chat-model types and the ``ChatModel`` protocol.

Everything above the adapter boundary (``chancel.agent``, and through it
``chancel.retriever`` / ``chancel.policy``) speaks only these types. No field
here is named after a vendor's wire format -- ``ToolCall.arguments`` is
always a parsed ``dict``, never a raw JSON string, regardless of whether the
underlying provider handed back an object (Anthropic) or a string that had
to be decoded first (OpenAI-compatible). That decoding, and everything else
provider-specific, happens inside ``chancel.providers.<name>`` and stops at
this file.

A provider that hands back arguments this module cannot make sense of --
unparseable JSON, or JSON that decodes to something other than an object --
must not raise. It must produce a normal ``ToolCall`` whose ``arguments`` is
exactly ``{"__malformed__": "<raw>"}``. The agent loop's tool executor
validates arguments before any retrieval happens, so a malformed call is
just another shape of "not a valid query" to it -- it becomes an error
``ToolResult``, never a crash. This is what keeps a hostile or broken model
from taking down the loop with a bad payload instead of a request the gate
can evaluate and deny.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel

MALFORMED_KEY = "__malformed__"


class ToolSpec(BaseModel, frozen=True):
    """One tool offered to the model, in JSON-Schema-parameter form."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


class ToolCall(BaseModel, frozen=True):
    """A tool invocation the model requested. ``arguments`` is always a
    parsed dict -- see module docstring for the malformed-input contract."""

    id: str
    name: str
    arguments: dict[str, Any]


class ToolResult(BaseModel, frozen=True):
    """The outcome of executing one ``ToolCall``, handed back to the model."""

    call_id: str
    content: str
    is_error: bool = False


class ChatTurn(BaseModel, frozen=True):
    """One turn of conversation history.

    ``role="tool_result"`` turns carry one or more ``ToolResult``s (a model
    may issue several tool calls in one turn); ``role="assistant"`` turns
    may carry ``tool_calls`` alongside (or instead of) text, reflecting what
    the model itself just requested so the next round has full context.
    """

    role: Literal["user", "assistant", "tool_result"]
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()


class ModelReply(BaseModel, frozen=True):
    """What ``ChatModel.complete`` hands back for one round."""

    text: str
    tool_calls: tuple[ToolCall, ...]


class ChatModel(Protocol):
    """The only interface the agent loop talks to. No concrete provider name
    or ``isinstance`` check against one may appear above this boundary."""

    name: str

    def complete(
        self, system: str, turns: Sequence[ChatTurn], tools: Sequence[ToolSpec]
    ) -> ModelReply: ...


def normalize_tool_arguments(raw: object) -> dict[str, Any]:
    """Coerce a provider's raw tool-call arguments into the neutral shape.

    ``raw`` is either already a parsed object (Anthropic's ``tool_use.input``)
    or a JSON-encoded string that must be decoded first (OpenAI-compatible's
    ``function.arguments``). A dict passes through unchanged. Anything that
    isn't a JSON string decoding to a dict -- an unparseable string, a string
    that decodes to a list or scalar, or some other object entirely --
    becomes ``{"__malformed__": "<raw>"}`` per the module-level contract.
    Shared here because both adapters need the exact same fallback shape.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {MALFORMED_KEY: raw}
        if isinstance(parsed, dict):
            return parsed
        return {MALFORMED_KEY: raw}
    return {MALFORMED_KEY: repr(raw)}
