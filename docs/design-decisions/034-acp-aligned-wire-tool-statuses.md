# DD-034: Align Live Tool Statuses With ACP Without Rewriting Traces

**Status:** Accepted
**Date:** 2026-08-11
**Related:** [017 Session Logging and Eval Format](017-session-logging-and-eval-format.md), [018 Event API Naming](018-event-api-naming.md), [025 Interruptible Agent Steps](025-interruptible-agent-steps.md), [027 Wire-only Structured Tool Output](027-wire-only-structured-tool-output.md), [028 ACP Ordered Event Bridge](028-acp-ordered-event-bridge.md)

## Decision

ConnectOnion keeps its established IO event names and fields. Live tool events
use ACP's lifecycle statuses:

| ConnectOnion event | Accepted producer statuses | Live wire status |
|---|---|---|
| `tool_call` | omitted, `pending`, `running`, `in_progress` | `pending` or `in_progress` |
| `tool_result` | `success`, `done`, `completed` | `completed` |
| `tool_result` | `error`, `failed`, `not_found`, `interrupted` | `failed` |

One pure normalizer returns a detached event at both live producer boundaries:
Agent trace streaming and provider-facing `IO.log`. Unknown or missing terminal
statuses are rejected instead of being displayed as success.

Canonical session traces do not change. They retain `success`, `error`,
`not_found`, and `interrupted` under DD-017, while only the detached IO copy is
normalized. Replay and rolling-upgrade consumers accept both vocabularies and
reduce them to the existing UI states `running`, `done`, and `error`.

Every `tool_result` has a preceding `tool_call` with the same `tool_id`,
including an unknown tool. This lets the ACP bridge issue a start before an
update and gives all clients a stable correlation target.

## Vocabulary boundary

The gap with ACP is deliberately not removed by renaming events:

- `tool_call` already maps directly to ACP `tool_call`.
- `tool_result` maps to ACP `tool_call_update` because ConnectOnion models a
  terminal result while ACP models partial updates.
- `thinking` and `assistant` map to ACP thought/message chunks.
- `approval_needed` remains ConnectOnion's synchronous policy boundary and is
  translated to ACP's asynchronous `session/request_permission` by DD-030.
- `llm_call`, `llm_result`, and `session_sync` remain internal presentation or
  persistence events with no ACP peer.

IDs, names, arguments, results, and wire-only `raw_output` remain unchanged.
The pure ACP mapper continues to create the official content models and camel-
case serialization required by the pinned SDK.

## Why

Event names and fields are already consumed by Python `RemoteAgent` and the
browser connection layer in `@connectonion/react`, which is the only SDK used
by oo-chat. Renaming them would require a dual-vocabulary migration without
eliminating the content and permission conversion that ACP necessarily
requires.

Status is the useful shared layer. ACP 0.12 and the current stable v1 protocol
both use `pending`, `in_progress`, `completed`, and `failed`. Provider adapters
can emit those states directly, and the ACP mapper no longer has to translate
the normal path.

Keeping persistence separate prevents a wire compatibility improvement from
rewriting historical logs, eval fixtures, session snapshots, or hooks that
inspect canonical tool outcomes.

## Compatibility and rollout

Python and `@connectonion/react` consumers recognize old and new
success/failure values. The React package's browser mapper treats every
unknown terminal status as an error so a newer server cannot be presented as
successful by accident. oo-chat needs no direct change because it renders the
React package's normalized ChatItems.

The Codex adapter now emits `in_progress`, `completed`, and `failed`. The
Claude Code JSON adapter has no intermediate activity stream, so its final
result envelope is outside this IO event contract.

## Rejected alternatives

- **Rename all events to ACP discriminators:** breaks established Python and
  React consumers and still requires translation for content and approval.
- **Rewrite canonical trace statuses:** changes persisted data, hook semantics,
  and eval fixtures for no protocol benefit.
- **Normalize only in the ACP mapper:** leaves provider adapters and other live
  clients on divergent status vocabularies.
- **Treat unknown status as success:** creates a fail-open presentation bug and
  can hide provider or protocol drift.
- **Add duplicate ACP field aliases to every event:** duplicates IDs, names,
  inputs, and results without reducing the boundary's semantic work.

## Reference

- [ACP v1 tool calls](https://agentclientprotocol.com/protocol/v1/tool-calls)
