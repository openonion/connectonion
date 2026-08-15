# Codex tool ↔ frontend integration contract

**Historical note.** The backend `codex` tool originally flattened Codex steps
into generic tool cards. Alpha.2 keeps those events as the compatibility
fallback and additionally emits the parented provider-invocation contract
described in [Coding-agent plugins](concepts/coding-agent-plugins.md).

## How the `codex` tool drives Codex

The tool (`connectonion/useful_tools/codex.py`) is **our own Python client** for
Codex's built-in **`codex app-server`** — OpenAI's native JSON-RPC 2.0 protocol
(newline-delimited over stdio). It does not add a second adapter dependency and
it is not headless `codex exec`.

Why app-server:

| | headless `codex exec` | **codex app-server (chosen)** |
|---|---|---|
| dependency | `codex` CLI | `codex` CLI only |
| whose code is the adapter | — | **ours (Python)** |
| session + resume | parse JSONL / `resume` | `thread/start` + `thread/resume` |
| interactive approval callbacks | ❌ none (sandbox only) | ✅ | ✅ `item/*/requestApproval` |
| official / stable | yes | third-party wrapper | **yes (OpenAI, powers every surface)** |
| create session w/o auth | n/a | ❌ needs auth | ✅ (auth only for the model turn) |

app-server wins on every axis for a Python framework: one dependency, official
protocol, our own client, and it still gives session/resume, live streaming, and
interactive approval requests when the selected Codex policy requires them.

## The original generic frontend contract

The connection layer bundled in `@connectonion/react`
(`connectonion-react/src/connect/chat-item-mapper.ts`) maps a **fixed set of
server io events** to the `ChatItem`s oo-chat renders. The codex tool emits only
events already in that vocabulary:

| Codex app-server event | tool emits `agent.io.log(...)` | SDK renders |
|---|---|---|
| `item/started` (commandExecution, fileChange, mcpToolCall, webSearch) | `tool_call` `{tool_id, name, args, status: in_progress}` | running tool card |
| `item/completed` (same item) | `tool_result` `{tool_id, status: completed\|failed}` | card completes / errors |
| `item/completed` (agentMessage) | — (returned as the tool result `last_message`) | agent's own reply |
| `item/*/requestApproval` (server → client) | `agent.io.request_approval(...)` → `approval_needed` | approval card, answer flows back |

Key points:

- **Stable `tool_id`**: `tool_call` and its `tool_result` share the item id so the
  SDK correlates them (`chat-item-mapper.ts` finds the tool_call by id).
- **Stable live status**: provider events use `in_progress`, `completed`,
  and `failed`. The SDK also accepts the historical success/failure values;
  canonical session traces keep their existing statuses.
- **Generic compatibility remains.** `tool_call` / `tool_result` are still
  emitted, now with optional provider-invocation correlation fields. Clients
  that understand `provider_invocation` nest them; older clients render them
  as ordinary cards.
- **Approval is already wired.** When Codex requests permission,
  `agent.io.request_approval` sends `approval_needed`
  and blocks for the user's answer over the same channel oo-chat already uses for
  every other tool's approval, so Codex's permission prompts render as normal
  approval cards with zero new code. The response is encoded per method: current
  command/file requests use `accept`/`decline`, permissions requests grant only
  the requested profile, and legacy methods retain their legacy decision shape.

## What the frontend team should know

- The React package owns normalization and child correlation. O Chat consumes
  its typed `provider_invocation` item and renders the shared coding-agent card.
- Generic tool cards remain the rolling-upgrade fallback.

## Validation

Verified end-to-end against the real `codex` 0.145.0 `app-server`: `initialize`
+ `thread/start` return a real thread id with no auth; `turn/start` runs and the
tool surfaces the real auth error cleanly when unauthenticated. Unit tests cover
the native-event conversion and the approval gate; the real-binary e2e lives in
`tests/e2e/real_api/test_real_codex.py`.
