"""Cassette-backed tests for the Anthropic adapter. No network, no key.

Cassette bodies in ``tests/cassettes/anthropic/`` are hand-written from the
shapes documented in ``PRPs/ai_docs/provider-apis.md``. Requests are
captured via ``httpx.MockTransport`` so we can assert on the exact wire
shape the adapter sent, not just the ``ModelReply`` it parsed back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

anthropic = pytest.importorskip("anthropic")
httpx = pytest.importorskip("httpx")

from chancel.providers.anthropic import AnthropicModel  # noqa: E402
from chancel.providers.base import ChatTurn, ToolCall, ToolResult, ToolSpec  # noqa: E402

CASSETTES = Path(__file__).resolve().parent.parent / "cassettes" / "anthropic"

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


def _model_with_response(body: dict[str, Any], captured: list[dict[str, Any]]) -> AnthropicModel:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return AnthropicModel(model="claude-sonnet-5", api_key="test", http_client=client)


def test_tool_use_response_parses_to_tool_call_and_sends_exact_field_names() -> None:
    captured: list[dict[str, Any]] = []
    model = _model_with_response(_load("tool_use_response.json"), captured)

    reply = model.complete("system prompt", [ChatTurn(role="user", text="hello")], [_TOOL])

    assert reply.text == ""
    assert len(reply.tool_calls) == 1
    call = reply.tool_calls[0]
    assert call.name == "search_matter_context"
    assert call.arguments == {"query": "contamination damages"}

    sent = captured[0]
    assert sent["system"] == "system prompt"
    assert sent["tools"] == [
        {
            "name": "search_matter_context",
            "description": "search the current matter",
            "input_schema": _TOOL.parameters,
        }
    ]
    assert "parameters" not in sent["tools"][0]
    assert sent["messages"] == [{"role": "user", "content": "hello"}]


def test_final_text_response_and_tool_result_message_mapping() -> None:
    captured: list[dict[str, Any]] = []
    model = _model_with_response(_load("final_text_response.json"), captured)

    turns = [
        ChatTurn(role="user", text="hello"),
        ChatTurn(
            role="assistant",
            tool_calls=(
                ToolCall(
                    id="toolu_01Search", name="search_matter_context", arguments={"query": "x"}
                ),
            ),
        ),
        ChatTurn(
            role="tool_result",
            tool_results=(
                ToolResult(call_id="toolu_01Search", content="passage text", is_error=False),
            ),
        ),
    ]

    reply = model.complete("system prompt", turns, [_TOOL])

    assert reply.tool_calls == ()
    expected_text = "Based on the retrieved passages, the matter concerns contamination damages."
    assert reply.text == expected_text

    sent_messages = captured[0]["messages"]
    assert sent_messages[1] == {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_01Search",
                "name": "search_matter_context",
                "input": {"query": "x"},
            }
        ],
    }
    assert sent_messages[2] == {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_01Search",
                "content": "passage text",
                "is_error": False,
            }
        ],
    }


def test_malformed_non_dict_input_produces_malformed_marker() -> None:
    # Anthropic hands back `input` as an already-parsed object, but a
    # misbehaving vendor response could send something else. Assert the
    # adapter treats a non-dict input as malformed rather than crashing the
    # agent loop.
    body = _load("tool_use_response.json")
    body["content"][0]["input"] = "not-a-dict"
    captured: list[dict[str, Any]] = []
    model = _model_with_response(body, captured)

    reply = model.complete("system", [ChatTurn(role="user", text="hi")], [_TOOL])

    assert reply.tool_calls[0].arguments == {"__malformed__": "not-a-dict"}


def test_no_tools_sends_no_tools_field() -> None:
    captured: list[dict[str, Any]] = []
    model = _model_with_response(_load("final_text_response.json"), captured)

    model.complete("system", [ChatTurn(role="user", text="hi")], [])

    assert "tools" not in captured[0]
