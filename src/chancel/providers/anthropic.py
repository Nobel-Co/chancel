"""Anthropic Messages API adapter. Optional dependency: ``pip install chancel[anthropic]``.

Field mapping is exact against ``PRPs/ai_docs/provider-apis.md`` -- that file
is what this module is written from, and it must not drift from it silently:

- ``system`` is a top-level request parameter, not a message.
- Tools are sent as-is with ``input_schema`` (not ``parameters``).
- An assistant ``tool_use`` content block maps to a ``ToolCall``; ``input``
  is already a parsed object there, but is normalized anyway in case a
  misbehaving vendor response hands back something else.
- A ``tool_result`` turn maps to a ``user`` message carrying one
  ``tool_result`` content block per ``ToolResult``, keyed on
  ``tool_use_id``.
- Text and tool_use blocks may coexist in one response; both are extracted.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from chancel.providers.base import (
    ChatTurn,
    ModelReply,
    ToolCall,
    ToolSpec,
    normalize_tool_arguments,
)

DEFAULT_MODEL = "claude-sonnet-5"
_MAX_TOKENS = 4096


def _to_anthropic_message(turn: ChatTurn) -> dict[str, Any]:
    if turn.role == "tool_result":
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": result.call_id,
                    "content": result.content,
                    "is_error": result.is_error,
                }
                for result in turn.tool_results
            ],
        }
    if turn.role == "assistant" and turn.tool_calls:
        content: list[dict[str, Any]] = []
        if turn.text:
            content.append({"type": "text", "text": turn.text})
        for call in turn.tool_calls:
            content.append(
                {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
            )
        return {"role": "assistant", "content": content}
    return {"role": turn.role, "content": turn.text}


class AnthropicModel:
    """``ChatModel`` over the Anthropic Messages API."""

    name: str = "anthropic"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        *,
        http_client: Any | None = None,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "the anthropic adapter requires the 'anthropic' package; "
                "install it with `pip install chancel[anthropic]`"
            ) from exc

        self.model = model or os.environ.get("CHANCEL_MODEL") or DEFAULT_MODEL
        resolved_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY")

        client_kwargs: dict[str, Any] = {"api_key": resolved_key}
        if http_client is not None:
            client_kwargs["http_client"] = http_client
        self._client = anthropic.Anthropic(**client_kwargs)

    def complete(
        self, system: str, turns: Sequence[ChatTurn], tools: Sequence[ToolSpec]
    ) -> ModelReply:
        messages = [_to_anthropic_message(turn) for turn in turns]
        anthropic_tools = [
            {"name": tool.name, "description": tool.description, "input_schema": tool.parameters}
            for tool in tools
        ]

        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": _MAX_TOKENS,
            "system": system,
            "messages": messages,
        }
        if anthropic_tools:
            request_kwargs["tools"] = anthropic_tools

        response = self._client.messages.create(**request_kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(block.text)
            elif block_type == "tool_use":
                arguments = normalize_tool_arguments(block.input)
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=arguments))

        return ModelReply(text="".join(text_parts), tool_calls=tuple(tool_calls))
