# Provider API Documentation Cache

**Fetched:** 2026-08-19  
**Sources:** platform.claude.com (Anthropic), developers.openai.com (OpenAI)

---

## ANTHROPIC Messages API

**Official documentation:** https://platform.claude.com/docs/en/api/messages  
**Tool use documentation:** https://platform.claude.com/docs/en/docs/build-with-claude/tool-use

### Request Structure

**Endpoint:** `POST /v1/messages`

**Required Headers:**
```
Content-Type: application/json
anthropic-version: 2023-06-01
X-Api-Key: $ANTHROPIC_API_KEY
```

**Request Body - Core Fields:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `model` | string | yes | e.g. `"claude-opus-5"`, `"claude-sonnet-4-5-20250929"`, `"claude-haiku-4-5-20251001"` |
| `max_tokens` | integer | yes | Maximum tokens in response |
| `messages` | array | yes | Array of message objects with `role` ("user"/"assistant") and `content` |
| `system` | string or array | no | System prompt; can be plain text or array of content blocks |
| `tools` | array | no | Array of tool definitions |
| `temperature` | number | no | 0.0 to 1.0 |
| `stream` | boolean | no | Default false |

**Tool Definition Structure:**
```json
{
  "name": "tool_name",
  "description": "What this tool does",
  "input_schema": {
    "type": "object",
    "properties": {
      "param_name": {
        "type": "string",
        "description": "Parameter description"
      }
    },
    "required": ["param_name"]
  }
}
```

**Tool Definition Fields:**
- `name` (string, required): Tool identifier
- `description` (string): What the tool does
- `input_schema` (object, required): JSON Schema defining inputs
- `strict` (boolean, optional): Enable schema validation
- `cache_control` (object, optional): Cache breakpoint

### Response Structure

**Message Object:**
```json
{
  "id": "msg_013Zva2CMHLNnXjNJJKqJ2EF",
  "type": "message",
  "role": "assistant",
  "model": "claude-opus-5",
  "content": [],
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 2095,
    "output_tokens": 503
  }
}
```

**Content Blocks Array - Tool Use Block:**
```json
{
  "type": "tool_use",
  "id": "toolu_01D7FLrfh4GYq7yT1ULFeyMV",
  "name": "tool_name",
  "input": {
    "param": "value"
  }
}
```

**Tool Use Block Fields:**
- `type` (string): `"tool_use"`
- `id` (string): Unique tool invocation ID
- `name` (string): The tool name being called
- `input` (object): Tool parameters as an object

**Stop Reason Values:**
- `"end_turn"` - Model naturally completed
- `"max_tokens"` - Reached max_tokens limit
- `"stop_sequence"` - Hit custom stop sequence
- `"tool_use"` - Model invoked tool(s)
- `"refusal"` - Policy violation detected
- `"model_context_window_exceeded"` - Context limit hit

### Returning Tool Results

**User Message with Tool Result:**
```json
{
  "role": "user",
  "content": [
    {
      "type": "tool_result",
      "tool_use_id": "toolu_01D7FLrfh4GYq7yT1ULFeyMV",
      "content": "Result string or content blocks",
      "is_error": false
    }
  ]
}
```

**Tool Result Block Fields:**
- `type` (string): `"tool_result"`
- `tool_use_id` (string, required): ID from the tool_use block
- `content` (string, optional): Result content
- `is_error` (boolean, optional): Flag for error results
- `cache_control` (object, optional): Cache breakpoint

### Current Model Names

```
claude-opus-5
claude-opus-4-8
claude-opus-4-7
claude-opus-4-6
claude-opus-4-5
claude-opus-4-5-20251101
claude-sonnet-5
claude-sonnet-4-6
claude-sonnet-4-5
claude-sonnet-4-5-20250929
claude-haiku-4-5
claude-haiku-4-5-20251001
```

---

## OPENAI-COMPATIBLE Chat Completions

**Official documentation:** https://developers.openai.com/api/docs/api-reference/chat/create  
**Function calling guide:** https://developers.openai.com/api/docs/guides/function-calling

### Request Structure

**Endpoint:** `POST /v1/chat/completions` (or with custom `base_url` for Groq, Together, OpenRouter, vLLM, Ollama)

**Request Body - Core Fields:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `model` | string | yes | e.g. `"gpt-4o"`, `"gpt-4-turbo"`, model ID for provider |
| `messages` | array | yes | Array of message objects with `role` and `content` |
| `tools` | array | no | Array of tool definitions with `type: "function"` wrapper |
| `tool_choice` | string or object | no | `"auto"`, `"required"`, `"none"`, or specific tool reference |
| `temperature` | number | no | Sampling temperature |
| `stream` | boolean | no | Default false |

**Tool Definition Structure:**
```json
{
  "type": "function",
  "function": {
    "name": "tool_name",
    "description": "What this tool does",
    "parameters": {
      "type": "object",
      "properties": {
        "param_name": {
          "type": "string",
          "description": "Parameter description"
        }
      },
      "required": ["param_name"],
      "additionalProperties": false
    }
  }
}
```

**Tool Definition Fields (inside `function`):**
- `name` (string, required): Tool identifier
- `description` (string, optional): When and how to use it
- `parameters` (object, required): JSON Schema defining inputs
- `strict` (boolean, optional): Enforce strict schema adherence

### Response Structure

**Choices Array - Message with Tool Calls:**
```json
{
  "choices": [
    {
      "finish_reason": "tool_calls",
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_abc123xyz",
            "type": "function",
            "function": {
              "name": "tool_name",
              "arguments": "{\"param\": \"value\"}"
            }
          }
        ]
      }
    }
  ]
}
```

**Tool Calls Array - Tool Call Object:**
- `id` (string): Unique tool call identifier
- `type` (string): `"function"` (only value currently supported)
- `function` (object):
  - `name` (string): The function name being called
  - `arguments` (string): **JSON-encoded arguments as a string** (must be parsed by client)

**Finish Reason Values:**
- `"tool_calls"` - Model invoked one or more tools
- `"stop"` - Natural completion
- `"length"` - Hit token limit
- `"content_filter"` - Content policy violation

### Returning Tool Results

**User Message with Tool Result:**
```json
{
  "role": "tool",
  "tool_call_id": "call_abc123xyz",
  "content": "Result content"
}
```

**Tool Result Message Fields:**
- `role` (string): `"tool"` (literal)
- `tool_call_id` (string, required): ID from the tool_calls array
- `content` (string, required): Result content

---

## API DIFFERENCES TABLE

| Aspect | Anthropic | OpenAI-Compatible |
|--------|-----------|-------------------|
| **Request Endpoint** | `POST /v1/messages` | `POST /v1/chat/completions` |
| **Tool Array** | Direct array of tool objects | Array wrapped with `type: "function"` |
| **Tool Definition** | Top-level `name`, `description`, `input_schema` | Nested under `function`: `name`, `description`, `parameters` |
| **Tool Schema Field** | `input_schema` (JSON Schema object) | `parameters` (JSON Schema object) |
| **Tool Choice Parameter** | Not in standard request (implicit behavior) | `tool_choice` string or object |
| **Model Invokes Tool** | Returns content block with `type: "tool_use"` | Returns message with `tool_calls` array |
| **Tool Use Block** | `{ type: "tool_use", id, name, input }` | `{ id, type: "function", function: { name, arguments } }` |
| **Tool Input** | `input` (object, parsed) | `arguments` (JSON string, requires parsing) |
| **Stop Reason for Tools** | `"tool_use"` | `"tool_calls"` |
| **Return Tool Result** | User message with `tool_result` content block | User message with `role: "tool"` |
| **Result Identifier** | `tool_use_id` field | `tool_call_id` field |
| **System Prompt** | `system` parameter (string or array) | System message in `messages` array with `role: "system"` |

---

## Provider-Specific Notes

### Anthropic
- Tool schemas use strict JSON Schema validation
- `input` is returned as an object (already parsed)
- Multiple tools can be called in one response
- Tool use round-trip requires re-sending tool results to get model's final answer

### OpenAI-Compatible (Base URL Pattern)
- Same Chat Completions API works across:
  - OpenAI (base_url: `https://api.openai.com/v1`)
  - Groq, Together, OpenRouter, vLLM, Ollama (custom base_url)
- `arguments` field is JSON stringified; client must `JSON.parse()`
- Tool calling models may behave differently per provider
- Some providers may not support all `tool_choice` options

### Differences in Actual Practice
- Anthropic returns tool arguments as native objects
- OpenAI returns tool arguments as JSON strings
- Anthropic `tool_use_id` vs OpenAI `tool_call_id` naming
- Anthropic supports more complex tool result structures (nested content blocks)
- OpenAI tool results are simpler (string content in `role: "tool"` message)
