# Adding a provider

A "provider" is a `ChatModel`: the thing the agent loop talks to. Adding one is implementing a
single protocol and passing the conformance suite. Nothing above the adapter boundary — not the
agent, not the retriever, not the gate — can tell which provider is answering, so a new adapter
**cannot weaken the isolation guarantee** even if it wants to. The wall is `PolicyGate`, and no
provider can reach it.

## The contract

`ChatModel` (in `chancel/providers/base.py`) is one attribute and one method:

```python
class ChatModel(Protocol):
    name: str

    def complete(
        self, system: str, turns: Sequence[ChatTurn], tools: Sequence[ToolSpec]
    ) -> ModelReply: ...
```

You speak only **neutral types** — `ChatTurn`, `ToolSpec`, `ToolCall`, `ModelReply`. No field is
named after a vendor's wire format, and a CI grep enforces that no provider name or `isinstance`
check leaks above this boundary. The one rule with teeth: `ToolCall.arguments` is *always* a
parsed `dict`. If your API hands back a JSON string, decode it with the shared
`normalize_tool_arguments()` helper — and if it hands back something unparseable, that helper
returns `{"__malformed__": "<raw>"}` rather than raising, so a broken model becomes an error
result instead of a crash.

## A minimal adapter, end to end

This adapter wraps a hypothetical HTTP chat API. It is complete — roughly forty lines.

```python
# src/chancel/providers/example_http.py
from __future__ import annotations

from collections.abc import Sequence

import httpx

from chancel.providers.base import (
    ChatModel,
    ChatTurn,
    ModelReply,
    ToolCall,
    ToolSpec,
    normalize_tool_arguments,
)


class ExampleHTTPModel:
    """A ChatModel over a generic /chat endpoint."""

    name = "example_http"

    def __init__(self, *, base_url: str, model: str) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=30.0)
        self._model = model

    def complete(
        self, system: str, turns: Sequence[ChatTurn], tools: Sequence[ToolSpec]
    ) -> ModelReply:
        payload = {
            "model": self._model,
            "system": system,
            "messages": [{"role": t.role, "content": t.text} for t in turns],
            "tools": [
                {"name": s.name, "description": s.description, "parameters": s.parameters}
                for s in tools
            ],
        }
        data = self._client.post("/chat", json=payload).raise_for_status().json()

        calls = tuple(
            ToolCall(
                id=c["id"],
                name=c["name"],
                # arguments may arrive as a JSON string — normalize to a dict,
                # never raise on malformed input.
                arguments=normalize_tool_arguments(c["arguments"]),
            )
            for c in data.get("tool_calls", [])
        )
        return ModelReply(text=data.get("text", ""), tool_calls=calls)


_model: ChatModel = ExampleHTTPModel(base_url="http://localhost:8080", model="demo")
```

## Register it (optional)

To make it reachable by name from the CLI and the demo, add a branch to `build_provider()` in
`chancel/registry.py` — deferred-imported so an optional dependency never loads unless the
provider is actually requested:

```python
    if resolved_name == "example_http":
        from chancel.providers.example_http import ExampleHTTPModel

        return ExampleHTTPModel(
            base_url=resolved_base_url or "http://localhost:8080",
            model=resolved_model or "demo",
        )
```

Registration is only needed for name-based lookup; the conformance suite tests the *class*, not
the registry.

## Prove it drops in

```bash
uv run pytest tests/conformance
```

That is the whole acceptance criterion: **implement one protocol, pass `tests/conformance/`.**
You do not edit the suite. `tests/conformance/test_new_adapter_is_drop_in.py` already makes this
concrete — it defines a brand-new `ConstantChatModel` *inside the test file*, never registers it,
and runs it through the exact same assertion helpers the registered adapters use. It passes with
zero edits to the suite. An adapter that requires editing the suite is a design failure, not a
test failure — and that test is there to keep it that way.
