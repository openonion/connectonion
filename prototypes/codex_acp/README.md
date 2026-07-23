# PROTOTYPE: driving codex-acp via the Agent Client Protocol (ACP)

> **Graduated.** This spike now ships as the codex tool itself:
> `connectonion/useful_tools/codex.py` is ACP-only — `codex()` drives codex-acp
> directly (the CLI backend was dropped to avoid maintaining two transports).
> Codex's steps are streamed to the frontend in its NATIVE event vocabulary
> (`tool_call` / `tool_result`), and permission requests map to
> `agent.io.request_approval`, so no frontend/SDK change is needed. These files
> are kept as the standalone reference/demo (fake agent, no npm install needed).
> Real-binary coverage: `tests/e2e/real_api/test_real_codex.py` and
> `prototypes/codex_acp/test_real_codex_acp.py`.

A spike, not a shipped feature. Validates that ConnectOnion can play the ACP
**Client** role and drive **codex-acp** (the Agent) over JSON-RPC, mapping the
protocol's streamed updates onto ConnectOnion's `io` model — including the
approval round-trip that headless `codex exec` cannot do.

Related: issue #177, PR #226 (the subprocess `codex` tool this could later
back with an ACP transport behind the same tool signature).

## Run it

```bash
python prototypes/codex_acp/demo.py
python -m pytest prototypes/codex_acp/test_acp_prototype.py -q
```

Uses `fake_codex_acp.py` (a stand-in Agent) so it runs with no external
binary. Against the real adapter, swap the launch command for
`["npx", "-y", "@zed-industries/codex-acp"]` or a local `codex-acp`; nothing
else in the client changes.

## What the spike establishes

1. **Role fit.** In ACP the editor is the *Client* and the coding agent is the
   *Agent*. ConnectOnion drives codex-acp as the Client: spawn subprocess,
   speak newline-delimited JSON-RPC 2.0 on stdio (protocol on stdout, logs on
   stderr — same framing as MCP).

2. **Flow.** `initialize` → `session/new` (or `session/load` to resume) →
   `session/prompt`. The prompt request blocks until the turn ends
   (`stopReason`); progress arrives meanwhile as `session/update`
   notifications.

3. **Clean mapping to `io`.** Each `session/update` variant becomes a flat
   event the ConnectOnion tool would forward via `agent.io.log(...)`:

   | ACP `session/update` | fields used | ConnectOnion |
   |---|---|---|
   | `agent_message_chunk` | `content.text` | streamed assistant text |
   | `agent_thought_chunk` | `content.text` | reasoning |
   | `tool_call` | `toolCallId`, `title`, `kind`, `status` | tool-call started |
   | `tool_call_update` | `toolCallId`, `status`, `content` | tool-call progressed |
   | `plan` | `entries[]` | plan display |

4. **Permission is the payoff.** codex-acp sends `session/request_permission`
   (a request, with id) before sensitive actions. The client answers it — which
   on the ConnectOnion side becomes `agent.io.request_approval(tool, args)`.
   Headless `codex exec` has no approval at all (approval is always `never`, so
   sandbox level is the only knob). ACP restores interactive, per-action
   approval. The prototype exercises both allow and reject.

## ACP vs. the subprocess tool (PR #226)

| | subprocess `codex exec --json` (PR #226) | ACP client (this spike) |
|---|---|---|
| transport | one-shot process per call | long-lived process, JSON-RPC session |
| session id | parse `thread.started` from JSONL | `session/new` returns it directly |
| resume | `codex exec resume <id>` | `session/load` |
| live steps | ✅ stream JSONL items to io | ✅ `session/update` → io |
| per-action approval | ❌ none (sandbox only) | ✅ `session/request_permission` |
| provider portability | per-CLI flags & resume syntax | one client for any ACP agent |
| dependency | just the `codex` CLI | the `codex-acp` adapter |
| complexity | ~1 function, stdlib | JSON-RPC client + reader thread |

## What's NOT covered (before this could graduate)

- Run against the **real** `@zed-industries/codex-acp`, not the fake agent —
  verify exact `sessionUpdate` field names and `optionId`/permission `kind`
  values, which are pinned here from the spec/docs and may drift.
- `fs/read_text_file` / `fs/write_text_file` client-side handling (advertised
  as unsupported here so the agent does its own IO).
- Content blocks beyond text (image/audio), `plan` entry rendering, cancel
  (`session/cancel`), auth methods, and MCP server passthrough in `session/new`.
- Timeout / process-death handling and turning `on_permission` into a real
  `agent.io.request_approval` bridge.

## Recommendation

The ACP path is viable and maps *better* onto ConnectOnion's `io` than the raw
CLI, chiefly because of `session/request_permission`. Suggested graduation
path: keep the simple subprocess `codex` tool (PR #226) as the default, and add
an ACP-backed transport behind the same tool signature for users who want live
approval and provider portability — validated first against the real codex-acp
binary.
