# Codex tool ↔ frontend integration contract

**TL;DR — the frontend (oo-chat) and the connectonion-ts SDK need NO changes.**
The backend `codex` tool converts Codex's steps into the events the SDK already
renders. This note records the research behind that and the exact contract.

## How the `codex` tool drives Codex

The tool (`connectonion/useful_tools/codex.py`) is **our own Python client** for
Codex's built-in **`codex app-server`** — OpenAI's native JSON-RPC 2.0 protocol
(newline-delimited over stdio). It is *not* the external `@zed-industries/codex-acp`
Node adapter, and it is *not* headless `codex exec`.

Why app-server:

| | headless `codex exec` | codex-acp (ACP) | **codex app-server (chosen)** |
|---|---|---|---|
| dependency | `codex` CLI | `codex` **+ codex-acp Node binary** | `codex` CLI only |
| whose code is the adapter | — | Zed Industries (Rust/Node) | **ours (Python)** |
| session + resume | parse JSONL / `resume` | `session/load` | `thread/start` + `thread/resume` |
| per-action approval | ❌ none (sandbox only) | ✅ | ✅ `item/*/requestApproval` |
| official / stable | yes | third-party wrapper | **yes (OpenAI, powers every surface)** |
| create session w/o auth | n/a | ❌ needs auth | ✅ (auth only for the model turn) |

app-server wins on every axis for a Python framework: one dependency, official
protocol, our own client, and it still gives session/resume, live streaming, and
per-action approval.

## The frontend contract (why no frontend change is needed)

The connectonion-ts SDK (`src/connect/chat-item-mapper.ts`) maps a **fixed set of
server io events** to the `ChatItem`s oo-chat renders. The codex tool emits only
events already in that vocabulary:

| Codex app-server event | tool emits `agent.io.log(...)` | SDK renders |
|---|---|---|
| `item/started` (commandExecution, fileChange, mcpToolCall, webSearch) | `tool_call` `{tool_id, name, args}` | running tool card |
| `item/completed` (same item) | `tool_result` `{tool_id, status: done\|error}` | card completes / errors |
| `item/completed` (agentMessage) | — (returned as the tool result `last_message`) | agent's own reply |
| `item/*/requestApproval` (server → client) | `agent.io.request_approval(...)` → `approval_needed` | approval card, answer flows back |

Key points:

- **Stable `tool_id`**: `tool_call` and its `tool_result` share the item id so the
  SDK correlates them (`chat-item-mapper.ts` finds the tool_call by id).
- **No custom event type.** An earlier draft emitted `io.log("codex_event", …)`,
  which matched nothing in the mapper and would not render — that was the bug to
  fix. The fix is emitting the native `tool_call` / `tool_result` vocabulary.
- **Approval is already wired.** `agent.io.request_approval` sends `approval_needed`
  and blocks for the user's answer over the same channel oo-chat already uses for
  every other tool's approval, so Codex's per-action prompts render as normal
  approval cards with zero new code.

## What the frontend team should know

- Nothing to implement to make Codex render. Codex's inner command runs and file
  edits show up as ordinary tool cards; its permission prompts as ordinary
  approval cards.
- Optional polish (not required): a Codex-specific icon/label on tool cards whose
  origin is the codex tool. This is cosmetic — the generic tool-card rendering
  already works.

## Validation

Verified end-to-end against the real `codex` 0.145.0 `app-server`: `initialize`
+ `thread/start` return a real thread id with no auth; `turn/start` runs and the
tool surfaces the real auth error cleanly when unauthenticated. Unit tests cover
the native-event conversion and the approval gate; the real-binary e2e lives in
`tests/e2e/real_api/test_real_codex.py`.
