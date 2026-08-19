"""OpenAI-compatible Chat Completions adapter.

Covers OpenAI itself and any Chat Completions-compatible endpoint reached
via ``base_url``: Groq, Together, OpenRouter, vLLM, Ollama. Optional
dependency: ``pip install chancel[openai]``.

Field mapping is exact against ``PRPs/ai_docs/provider-apis.md``:

- The system prompt is a leading ``{"role": "system", ...}`` message, not a
  top-level parameter.
- Tools are wrapped: ``{"type": "function", "function": {name, description,
  parameters}}`` -- the schema field is ``parameters``, not ``input_schema``.
- A response tool call's ``function.arguments`` is a **JSON string**, not an
  object; it must be ``json.loads``-ed, and an unparseable or non-object
  result falls back to the shared ``{"__malformed__": ...}`` marker rather
  than raising.
- A ``tool_result`` turn maps to one ``role: "tool"`` message per
  ``ToolResult``, keyed on ``tool_call_id`` (not ``tool_use_id``).
"""

from __future__ import annotations

import json
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

DEFAULT_MODEL = "gpt-4o"


def _turn_to_openai_messages(turn: ChatTurn) -> list[dict[str, Any]]:
    if turn.role == "tool_result":
        return [
            {"role": "tool", "tool_call_id": result.call_id, "content": result.content}
            for result in turn.tool_results
        ]
    if turn.role == "assistant" and turn.tool_calls:
        return [
            {
                "role": "assistant",
                "content": turn.text or None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                    }
                    for call in turn.tool_calls
                ],
            }
        ]
    return [{"role": turn.role, "content": turn.text}]


class OpenAICompatModel:
    """``ChatModel`` over the OpenAI-compatible Chat Completions API."""

    name: str = "openai_compat"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        http_client: Any | None = None,
    ) -> None:
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "the openai_compat adapter requires the 'openai' package; "
                "install it with `pip install chancel[openai]`"
            ) from exc

        self.model = model or os.environ.get("CHANCEL_MODEL") or DEFAULT_MODEL
        resolved_base_url = base_url if base_url is not None else os.environ.get("CHANCEL_BASE_URL")
        resolved_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        if resolved_key is None and resolved_base_url is not None:
            # Local servers reached via base_url (Ollama and friends) don't
            # need a real key, but the SDK requires a non-empty string.
            resolved_key = "not-needed"

        client_kwargs: dict[str, Any] = {"api_key": resolved_key}
        if resolved_base_url is not None:
            client_kwargs["base_url"] = resolved_base_url
        if http_client is not None:
            client_kwargs["http_client"] = http_client
        self._client = openai.OpenAI(**client_kwargs)

    def complete(
        self, system: str, turns: Sequence[ChatTurn], tools: Sequence[ToolSpec]
    ) -> ModelReply:
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for turn in turns:
            messages.extend(_turn_to_openai_messages(turn))

        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

        request_kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if openai_tools:
            request_kwargs["tools"] = openai_tools

        response = self._client.chat.completions.create(**request_kwargs)
        message = response.choices[0].message

        tool_calls: list[ToolCall] = []
        for raw_call in message.tool_calls or []:
            arguments = normalize_tool_arguments(raw_call.function.arguments)
            tool_calls.append(
                ToolCall(id=raw_call.id, name=raw_call.function.name, arguments=arguments)
            )

        return ModelReply(text=message.content or "", tool_calls=tuple(tool_calls))
