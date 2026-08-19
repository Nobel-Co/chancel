"""Cassette-backed tests for the openai_compat adapter. No network, no key.

Cassette bodies in ``tests/cassettes/openai/`` are hand-written from the
shapes documented in ``PRPs/ai_docs/provider-apis.md``. Requests are
captured via ``httpx2.MockTransport`` (the openai SDK build in this
environment vendors ``httpx2`` rather than ``httpx``) so we can assert on
the exact wire shape sent, not just the ``ModelReply`` parsed back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

openai = pytest.importorskip("openai")
httpx2 = pytest.importorskip("httpx2")

from chancel.providers.base import ChatTurn, ToolCall, ToolResult, ToolSpec  # noqa: E402
from chancel.providers.openai_compat import OpenAICompatModel  # noqa: E402

CASSETTES = Path(__file__).resolve().parent.parent / "cassettes" / "openai"

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


def _load(name: str) -> dict[str, Any]:
    return json.loads((CASSETTES / name).read_text())  # type: ignore[no-any-return]


def _model_with_response(body: dict[str, Any], captured: list[dict[str, Any]]) -> OpenAICompatModel:
    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(json.loads(request.content))
        return httpx2.Response(200, json=body)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    return OpenAICompatModel(model="gpt-4o", api_key="test", http_client=client)


def test_tool_calls_response_parses_json_string_arguments_and_sends_function_wrapper() -> None:
    captured: list[dict[str, Any]] = []
    model = _model_with_response(_load("tool_calls_response.json"), captured)

    reply = model.complete("system prompt", [ChatTurn(role="user", text="hello")], [_TOOL])

    assert len(reply.tool_calls) == 1
    call = reply.tool_calls[0]
    assert call.name == "search_matter_context"
    assert call.arguments == {"query": "contamination damages"}

    sent = captured[0]
    assert sent["messages"][0] == {"role": "system", "content": "system prompt"}
    assert sent["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search_matter_context",
                "description": "search the current matter",
                "parameters": _TOOL.parameters,
            },
        }
    ]
    assert "input_schema" not in sent["tools"][0]["function"]


def test_malformed_json_string_produces_malformed_marker() -> None:
    captured: list[dict[str, Any]] = []
    model = _model_with_response(_load("malformed_arguments_response.json"), captured)

    reply = model.complete("system", [ChatTurn(role="user", text="hi")], [_TOOL])

    assert reply.tool_calls[0].arguments == {"__malformed__": "{not json"}


def test_final_response_and_tool_result_message_mapping() -> None:
    captured: list[dict[str, Any]] = []
    model = _model_with_response(_load("final_response.json"), captured)

    turns = [
        ChatTurn(role="user", text="hello"),
        ChatTurn(
            role="assistant",
            tool_calls=(
                ToolCall(
                    id="call_01Search", name="search_matter_context", arguments={"query": "x"}
                ),
            ),
        ),
        ChatTurn(
            role="tool_result",
            tool_results=(
                ToolResult(call_id="call_01Search", content="passage text", is_error=False),
            ),
        ),
    ]

    reply = model.complete("system prompt", turns, [_TOOL])

    assert reply.tool_calls == ()
    expected_text = "Based on the retrieved passages, the matter concerns contamination damages."
    assert reply.text == expected_text

    sent_messages = captured[0]["messages"]
    assistant_msg = sent_messages[2]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["tool_calls"] == [
        {
            "id": "call_01Search",
            "type": "function",
            "function": {"name": "search_matter_context", "arguments": json.dumps({"query": "x"})},
        }
    ]

    tool_result_msg = sent_messages[3]
    assert tool_result_msg == {
        "role": "tool",
        "tool_call_id": "call_01Search",
        "content": "passage text",
    }


def test_no_tools_sends_no_tools_field() -> None:
    captured: list[dict[str, Any]] = []
    model = _model_with_response(_load("final_response.json"), captured)

    model.complete("system", [ChatTurn(role="user", text="hi")], [])

    assert "tools" not in captured[0]
