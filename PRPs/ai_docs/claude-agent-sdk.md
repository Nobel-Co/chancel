# Claude Agent SDK (Python) - Hooks & Permissions Cache

**Fetched 2026-08-19** from official Anthropic documentation  
**Package:** `claude-agent-sdk` (PyPI)

---

## 1. Hook Event Names (Python SDK)

**Source:** https://code.claude.com/docs/en/agent-sdk/hooks

Available hook event names as **exact strings** for the Python SDK:

| Event Name | What Triggers It | Python Support |
|-----------|------------------|-----------------|
| `PreToolUse` | Tool call request (can block or modify) | Yes |
| `PostToolUse` | Tool execution result | Yes |
| `PostToolUseFailure` | Tool execution failure | Yes |
| `UserPromptSubmit` | User prompt submission | Yes |
| `Stop` | Agent execution stop | Yes |
| `SubagentStart` | Subagent initialization | Yes |
| `SubagentStop` | Subagent completion | Yes |
| `PreCompact` | Conversation compaction request | Yes |
| `PermissionRequest` | A tool call needs a permission decision | Yes |
| `Notification` | Agent status messages | Yes |

**Not available in Python SDK** (TypeScript-only): `PostToolBatch`, `UserPromptExpansion`, `MessageDisplay`, `StopFailure`, `PostCompact`, `PermissionDenied`, `SessionStart`, `SessionEnd`, `TeammateIdle`, `TaskCreated`, `TaskCompleted`, `Elicitation`, `ElicitationResult`, `ConfigChange`, `InstructionsLoaded`, `WorktreeCreate`, `WorktreeRemove`, `CwdChanged`, `FileChanged`, `DirectoryAdded`.

---

## 2. PreToolUse Hook: Deny Return Shape (EXACT)

**Source:** https://code.claude.com/docs/en/agent-sdk/hooks (Example on line 63-69)

To **deny** a tool call in a `PreToolUse` hook, return this dict structure:

```python
{
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",  # Exact value
        "permissionDecision": "deny",  # Exact value
        "permissionDecisionReason": "Cannot modify .env files"  # String, required
    }
}
```

**Fields:**
- `hookSpecificOutput`: Required container for hook-specific decisions
  - `hookEventName`: Must be exactly `"PreToolUse"`
  - `permissionDecision`: One of `"allow"`, `"deny"`, `"ask"`, or `"defer"` (exact strings)
  - `permissionDecisionReason`: Human-readable reason (string); sent to Claude and user

**Other outcomes:**
- **Allow:** `{"hookSpecificOutput": {"permissionDecision": "allow", ...}}`
- **Ask for user approval:** `{"hookSpecificOutput": {"permissionDecision": "ask", "permissionDecisionReason": "..."}}`
- **Defer (pause for later):** `{"hookSpecificOutput": {"permissionDecision": "defer"}}`
- **Modify input:** Add `"updatedInput": {<modified tool args>}` to `hookSpecificOutput`

**Return empty to allow:** `{}`

---

## 3. Hook Registration on ClaudeAgentOptions (Python)

**Source:** https://code.claude.com/docs/en/agent-sdk/python (ClaudeAgentOptions dataclass)

```python
@dataclass
class ClaudeAgentOptions:
    hooks: dict[HookEvent, list[HookMatcher]] | None = None
```

**HookMatcher registration (Python):**

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(
                matcher="Write|Edit",  # Optional: regex or pipe-separated tool names
                hooks=[protect_env_files],  # List of async callback functions
                timeout=600  # Optional: timeout in seconds
            )
        ]
    }
)
```

**HookMatcher fields:**
- `matcher` (str, optional): Regex pattern or pipe-separated exact names. Examples:
  - `"Bash"` – exact tool name
  - `"Write|Edit|NotebookEdit"` – multiple tools
  - `"^mcp__"` – all MCP tools (regex)
  - Omitted/`None` – all tools of that event type
- `hooks` (list[async callable], required): Callback functions receiving `(input_data, tool_use_id, context)`
- `timeout` (int, optional): Seconds before hook times out; default varies by event (600s for most)

**Hook callback signature:**
```python
async def my_hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
    """Intercept agent behavior."""
    # Return permit/deny/defer decision in hookSpecificOutput
    return {}  # or return dict with hookSpecificOutput
```

---

## 4. Permission System: `can_use_tool` Callback API

**Source:** https://code.claude.com/docs/en/agent-sdk/python (CanUseTool callback type)

Alternative to hooks for permission control. Called **only when permission flow reaches a prompt** (earlier rules didn't auto-approve/deny).

**Callback registration:**

```python
from claude_agent_sdk import ClaudeAgentOptions, PermissionResultAllow, PermissionResultDeny

async def custom_permission(
    tool_name: str,
    input_data: dict[str, Any],
    context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """Custom permission logic."""
    if tool_name == "Bash" and "rm -rf" in input_data.get("command", ""):
        return PermissionResultDeny(message="Dangerous command blocked", interrupt=False)
    return PermissionResultAllow()

options = ClaudeAgentOptions(can_use_tool=custom_permission)
```

**Callback parameters:**
- `tool_name` (str): Name of the tool requesting permission
- `input_data` (dict[str, Any]): Tool's input arguments
- `context` (ToolPermissionContext): Metadata about the request
  - `decision_reason` (str | None): Why this permission was asked (forwarded from `PreToolUse` hook's `permissionDecisionReason`)
  - `tool_use_id`, `agent_id`, `blocked_path`, `title`, `display_name`, `description`

---

## 5. Permission Callback: Deny Return Shape (EXACT)

**Source:** https://code.claude.com/docs/en/agent-sdk/python (PermissionResultDeny)

To **deny** a tool in the `can_use_tool` callback:

```python
from claude_agent_sdk import PermissionResultDeny

@dataclass
class PermissionResultDeny:
    behavior: Literal["deny"] = "deny"
    message: str = ""
    interrupt: bool = False
```

**Return instance:**
```python
return PermissionResultDeny(
    message="System directory write not allowed",
    interrupt=False  # Whether to halt execution
)
```

**Allow alternative (PermissionResultAllow):**
```python
from claude_agent_sdk import PermissionResultAllow

@dataclass
class PermissionResultAllow:
    behavior: Literal["allow"] = "allow"
    updated_input: dict[str, Any] | None = None
    updated_permissions: list[PermissionUpdate] | None = None

# Return allow:
return PermissionResultAllow()
# Or allow with modified input:
return PermissionResultAllow(updated_input={**input_data, "file_path": safe_path})
```

---

## 6. Package Name & Version

**Source:** https://github.com/anthropics/claude-agent-sdk-python (README)

- **Package name:** `claude-agent-sdk` (PyPI)
- **Install:** `pip install claude-agent-sdk`
- **Min Python:** 3.10+
- **License:** MIT
- **Repo:** https://github.com/anthropics/claude-agent-sdk-python

**Version tracking:** No specific version pinned in docs. For latest, check PyPI or the repo's `CHANGELOG.md`.

---

## 7. Verdict: Which Mechanism for Hard Deny?

**Source:** https://code.claude.com/docs/en/agent-sdk/permissions (Permissions flow, step 1)

### **Both mechanisms exist; hooks are evaluated first and take priority:**

1. **Hooks (`PreToolUse`) — Primary mechanism for hard deny:**
   - Run **before** all other permission checks (deny rules, ask rules, permission mode, allow rules, `can_use_tool`)
   - Return `"deny"` blocks a tool call **even in `bypassPermissions` mode**
   - Documented example shows this as the standard pattern for blocking operations
   - Direct quote: *"A hook can deny the call outright or pass it on."* (step 1 of permissions flow)

2. **`can_use_tool` callback — Secondary, consulted only if earlier steps don't resolve:**
   - Called only when permission flow reaches the prompt stage
   - Cannot block calls already approved by `allowed_tools`, `bypassPermissions`, or `acceptEdits`
   - Return `PermissionResultDeny` blocks if the callback is reached

### **Documented recommendation:**

- **Use hooks for policy enforcement** that must apply regardless of permission mode
- **Use `can_use_tool` for interactive/contextual decisions** when you need user input or runtime context

**Quote from permissions flow:** *"A `PreToolUse` hook allow doesn't skip the deny and ask rules below; those are evaluated regardless of the hook result… A hook that returns `allow` does not skip the deny and ask rules below."* This shows hooks are the enforcement layer that persists across all other modes.

---

## 8. Unsourceable Items

- **TypeScript SDK hook types** — Not transcribed; only Python documented here. TypeScript equivalents (HookCallback, PreToolUseHookInput, etc.) are in https://code.claude.com/docs/en/agent-sdk/typescript but differ slightly in naming conventions (camelCase vs snake_case).
- **Exact version number** — Not stated in docs; check PyPI or CHANGELOG.md for latest.
- **Full hook type definitions** — Python SDK source code would have `HookEvent` and `HookInput` type unions; not fully enumerated in public docs.

---

## References

- **Hooks guide:** https://code.claude.com/docs/en/agent-sdk/hooks
- **Permissions guide:** https://code.claude.com/docs/en/agent-sdk/permissions
- **Python SDK reference:** https://code.claude.com/docs/en/agent-sdk/python
- **Agent SDK overview:** https://code.claude.com/docs/en/agent-sdk
- **GitHub repo:** https://github.com/anthropics/claude-agent-sdk-python
