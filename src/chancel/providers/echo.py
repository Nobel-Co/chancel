"""Deterministic, offline ``ChatModel``. No network, no API key.

Exists so the agent loop, the registry, and everything that tests them can
run cold-clone with zero external dependencies. ``EchoModel`` is not trying
to be a good conversational partner -- it has exactly one branch: has this
conversation already seen a ``tool_result`` turn, or not.

- Not yet: if it was offered any tools, call the first one with the last
  user turn's text as the query. This is what drives the agent loop's first
  round without needing a real model to decide to search.
- Already: summarize what came back. No randomness, no state beyond what is
  in ``turns`` -- the same ``turns`` always produces the same ``ModelReply``.
"""

from __future__ import annotations

from collections.abc import Sequence

from chancel.providers.base import ChatTurn, ModelReply, ToolCall, ToolSpec

# Passage separator contract with chancel.agent's tool executor: it joins
# each retrieved chunk's text with this separator when building a
# ToolResult's content. Only this adapter parses that structure back apart
# to count/preview passages -- a real provider just shows the content to the
# model as opaque text and never needs to agree on a separator at all.
_PASSAGE_SEPARATOR = "\n\n"


class EchoModel:
    """Deterministic offline ``ChatModel``. See module docstring."""

    name: str = "echo"

    def complete(
        self, system: str, turns: Sequence[ChatTurn], tools: Sequence[ToolSpec]
    ) -> ModelReply:
        del system  # echo never reads the system prompt -- it isn't "smart"
        has_tool_result = any(turn.role == "tool_result" for turn in turns)

        if tools and not has_tool_result:
            last_user_text = ""
            for turn in reversed(turns):
                if turn.role == "user":
                    last_user_text = turn.text
                    break
            call = ToolCall(id="echo-1", name=tools[0].name, arguments={"query": last_user_text})
            return ModelReply(text="", tool_calls=(call,))

        passages: list[str] = []
        for turn in turns:
            if turn.role != "tool_result":
                continue
            for result in turn.tool_results:
                if not result.content:
                    continue
                passages.extend(p for p in result.content.split(_PASSAGE_SEPARATOR) if p)

        previews = " ".join(f"[{p[:100]}]" for p in passages)
        prefix = f"Echo answer based on {len(passages)} retrieved passages:"
        text = f"{prefix} {previews}" if previews else prefix
        return ModelReply(text=text, tool_calls=())
