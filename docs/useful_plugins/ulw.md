# ulw (Ultra Light Work)

Autonomous agent mode: the agent keeps working turn after turn without asking for approval, until it reaches a checkpoint or declares itself "genuinely complete".

## Usage

```python
from connectonion import Agent
from connectonion.useful_plugins import tool_approval, ulw

agent = Agent("worker", plugins=[tool_approval, ulw])
```

Requires `tool_approval`. ULW is an explicit approval mode; there is no generic
`skip_tool_approval` flag.

## What it does

When activated through a trusted mode-control path:
1. Skips tool approval prompts while the server-owned runtime mode is `ulw`
2. After each turn completes, automatically starts another turn
3. At the turn limit (default: 100), pauses for user input
4. User can continue, extend turns, or switch back to safe mode

One ULW lease is capped at 1,000 turns. Invalid, negative, boolean, or oversized
turn budgets fail closed.

## How to trigger ULW mode

A hosted client requests ULW through a fully bound `session.input` action. The
top-level `INPUT` fields must match the signed payload:

```json
{
  "type": "INPUT",
  "to": "0xHostAddress",
  "session_id": "550e8400-...",
  "input_id": "7d8f...",
  "prompt": "Refactor the codebase",
  "mode": "ulw",
  "payload": {
    "action": "session.input",
    "to": "0xHostAddress",
    "session_id": "550e8400-...",
    "input_id": "7d8f...",
    "prompt": "Refactor the codebase",
    "mode": "ulw",
    "attachments_sha256": "5675eee946de112f65f01d6f509a96b9e444811b7705bae7ec0b66ec4ac2c821",
    "timestamp": 1702234567
  },
  "from": "0xCallerPublicKey",
  "signature": "0x..."
}
```

The digest shown is SHA-256 of canonical `{"files":[],"images":[]}`. The
preceding modern CONNECT must sign `action: "session.connect"` and the
`session_sha256` snapshot. A bare client `mode_change` cannot authorize ULW, and
neither can a mode placed in the round-tripped session. A modern hosted client
selects ULW only on a fully bound signed INPUT sent while the session is idle.
An INPUT received during a running turn is retryably rejected rather than
converted into an internal `mode_change`.

For trusted local code, use the dedicated `mode` argument:

```python
agent.input("Refactor the entire codebase to use async functions", mode="ulw")
```

Hosted HTTP code accepts a mode only from authenticated, signed control input.
Putting `mode`, `skip_tool_approval`, or ULW state in the client session does not
activate ULW.

## Session persistence and security

The client-returned session is untrusted. `plugin_state['ulw']` is only a UI
snapshot of turn progress; changing its `turns` or `turns_used` values cannot
activate ULW, reset its budget, or extend its lease.

Hosted ULW authority lives in server-only state bound to the authenticated caller
and session ID. It contains the validated mode and remaining turn lease and is
never returned as part of the client session. On reconnect, ULW resumes only from
that owner-bound state. An exhausted or malformed lease falls back to Safe mode.
Each explicit authorization receives a new lease generation; progress is
monotonic only within that generation, so stale checkpoints cannot reset a
budget while a genuine reauthorization can start a fresh one.

The current turn is consumed before privileged LLM/tool work. A live switch to
ULW consumes that already-running turn immediately. A live downgrade to Safe or
Plan is drained at every tool boundary, so later tools in the same LLM batch no
longer inherit ULW. An interrupt revokes ULW and cannot schedule another
automatic turn.

## Turn-based checkpoints

For a modern hosted, owner-bound session, reaching the server-owned lease limit
does not block on an unsigned control frame. The agent exits to Safe mode,
emits the normal `mode_changed` event, and completes its OUTPUT. To continue in
ULW, wait for OUTPUT and send a new fully bound signed INPUT with `mode: "ulw"`;
that explicit authorization creates a fresh bounded lease generation.

Trusted local and legacy interactive integrations can still use the blocking
checkpoint protocol. After reaching the limit, their frontend receives:

```json
{ "type": "ulw_turns_reached", "turns_used": 10, "max_turns": 10 }
```

Those local/legacy integrations can respond with:
- `{ "action": "continue", "turns": 10 }` — extend by N more turns
- `{ "action": "switch_mode", "mode": "safe" }` — return to safe mode
- Anything else — exit to safe mode

Without compatible interactive I/O (including HTTP and modern hosted signed
sessions), reaching the limit automatically expires the lease and returns to
Safe mode.

The built-in lease and replay state is process-local. Hosted ULW requires one
worker; `host(workers=N)` rejects `N != 1`, and external ASGI servers must also
run one worker unless they provide a shared transactional backend.

## Prompt injection mid-session

Trusted local and legacy interactive frontends can update the agent's goal
while it is working:

```json
{ "type": "prompt_update", "prompt": "Focus on the authentication module" }
```

This is injected into the system prompt before each LLM call. Modern hosted
sessions reject raw `prompt_update` because it is persistent intent without an
action-specific signature. Send the updated goal as the prompt of a later
fully bound signed INPUT after the current OUTPUT instead.

## When to use

- Large refactoring tasks
- Batch code generation
- Extended research and writing sessions
- Any autonomous work where you don't want to approve every tool call

## Events used

| Event | Handler | Purpose |
|-------|---------|---------|
| `after_user_input` | `restore_ulw_state` | Apply explicit trusted mode or owner-bound server state |
| `before_iteration` | `reconcile_ulw_mode` | Persist a switch back to Safe/Plan/Accept Edits |
| `before_llm` | `reconcile_ulw_mode_before_llm` | Recheck mode after all iteration handlers, regardless of plugin order |
| `on_complete` | `ulw_keep_working` | Start next turn if turns remain |
| `before_iteration` | `poll_prompt_update` | Check for goal updates from frontend |
| `before_llm` | `inject_ulw_prompt` | Inject current goal into system prompt |

## Source

```
connectonion/useful_plugins/ulw.py
```
