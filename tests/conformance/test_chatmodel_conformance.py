"""Conformance for the ``ChatModel`` protocol, parametrized across every
registered provider (``registry_conformance.PROVIDERS_ALL``).

``echo`` and ``hostile_echo`` run everywhere: no network, no key. They are
built directly. ``hostile_echo`` is being built by another agent on this
same PRP and may not exist yet on this branch -- construction is
``importorskip``-style guarded so this file collects and runs cleanly either
way (see ``chancel.registry.build_provider``'s own guard for the same
reason).

``anthropic`` and ``openai_compat`` have real SDK dependencies and would
normally need a live API key. Both adapters accept an injected HTTP client
(see ``tests/unit/test_provider_anthropic.py`` / ``test_provider_openai.py``),
so conformance drives them the same way: ``importorskip`` the SDK, then
build the model over an ``httpx``/``httpx2`` ``MockTransport`` that replays
one of the hand-written cassette bodies in ``tests/cassettes/``. No network,
no key, and the adapter's real request/response parsing is exercised, not
bypassed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _contracts import (
    assert_chatmodel_shape,
    assert_complete_contract,
    assert_idempotent,
    assert_tool_calls_well_formed,
)
from registry_conformance import PROVIDERS_OFFLINE

from chancel.providers.base import ChatTurn, ToolSpec

CASSETTES = Path(__file__).resolve().parent.parent / "cassettes"

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

CASSETTE_BACKED = ["anthropic", "openai_compat"]

_SYSTEM = "You are a matter-scoped assistant. Only answer from retrieved passages."
_USER_TURNS = [ChatTurn(role="user", text="What does the retainer clause say?")]


def _load(*parts: str) -> dict[str, Any]:
    path = CASSETTES.joinpath(*parts)
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def _build_offline(name: str) -> Any:
    if name == "echo":
        from chancel.providers.echo import EchoModel

        return EchoModel()
    if name == "hostile_echo":
        try:
            from chancel.providers.hostile_echo import HostileEchoModel
        except ImportError:
            pytest.skip("chancel.providers.hostile_echo not available on this branch yet")
        return HostileEchoModel()
    raise AssertionError(f"not an offline provider: {name!r}")


def _build_cassette_backed(name: str, body: dict[str, Any]) -> Any:
    if name == "anthropic":
        pytest.importorskip("anthropic")
        httpx = pytest.importorskip("httpx")
        from chancel.providers.anthropic import AnthropicModel

        def handler(request: Any) -> Any:
            return httpx.Response(200, json=body)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        return AnthropicModel(model="claude-sonnet-5", api_key="test", http_client=client)
    if name == "openai_compat":
        pytest.importorskip("openai")
        httpx2 = pytest.importorskip("httpx2")
        from chancel.providers.openai_compat import OpenAICompatModel

        def handler(request: Any) -> Any:
            return httpx2.Response(200, json=body)

        client = httpx2.Client(transport=httpx2.MockTransport(handler))
        return OpenAICompatModel(model="gpt-4o", api_key="test", http_client=client)
    raise AssertionError(f"not a cassette-backed provider: {name!r}")


def _tool_call_cassette(name: str) -> dict[str, Any]:
    if name == "anthropic":
        return _load("anthropic", "tool_use_response.json")
    return _load("openai", "tool_calls_response.json")


def _text_only_cassette(name: str) -> dict[str, Any]:
    if name == "anthropic":
        return _load("anthropic", "final_text_response.json")
    return _load("openai", "final_response.json")


# ---------------------------------------------------------------------------
# Offline providers: echo, hostile_echo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", PROVIDERS_OFFLINE)
def test_offline_has_name(name: str) -> None:
    model = _build_offline(name)
    assert_chatmodel_shape(model)


@pytest.mark.parametrize("name", PROVIDERS_OFFLINE)
def test_offline_tool_call_or_text_answer_never_names_unoffered_tool(name: str) -> None:
    model = _build_offline(name)
    reply = assert_complete_contract(model, _SYSTEM, _USER_TURNS, [_TOOL])
    assert_tool_calls_well_formed(reply, {_TOOL.name})


@pytest.mark.parametrize("name", PROVIDERS_OFFLINE)
def test_offline_is_idempotent(name: str) -> None:
    model = _build_offline(name)
    assert_idempotent(model, _SYSTEM, _USER_TURNS, [_TOOL])


# ---------------------------------------------------------------------------
# Cassette-backed providers: anthropic, openai_compat
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", CASSETTE_BACKED)
def test_cassette_backed_has_name(name: str) -> None:
    model = _build_cassette_backed(name, _text_only_cassette(name))
    assert_chatmodel_shape(model)


@pytest.mark.parametrize("name", CASSETTE_BACKED)
def test_cassette_backed_tool_call_names_offered_tool(name: str) -> None:
    model = _build_cassette_backed(name, _tool_call_cassette(name))
    reply = assert_complete_contract(model, _SYSTEM, _USER_TURNS, [_TOOL])
    assert reply.tool_calls, "expected the tool-use cassette to produce a tool call"
    assert_tool_calls_well_formed(reply, {_TOOL.name})


@pytest.mark.parametrize("name", CASSETTE_BACKED)
def test_cassette_backed_text_only_reply_is_well_shaped(name: str) -> None:
    model = _build_cassette_backed(name, _text_only_cassette(name))
    reply = assert_complete_contract(model, _SYSTEM, _USER_TURNS, [_TOOL])
    assert reply.tool_calls == ()
    assert reply.text


@pytest.mark.parametrize("name", CASSETTE_BACKED)
def test_cassette_backed_is_idempotent(name: str) -> None:
    # The mocked transport's handler always returns the same body regardless
    # of call count, so the adapter's own parsing is deterministic here even
    # though the real API would not be.
    model = _build_cassette_backed(name, _tool_call_cassette(name))
    assert_idempotent(model, _SYSTEM, _USER_TURNS, [_TOOL])
