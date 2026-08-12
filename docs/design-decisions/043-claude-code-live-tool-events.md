# DD-043: Stream Claude Code tool activity through native Agent IO

**Status:** Accepted

**Date:** 2026-08-12

**Related:** [018 Event API Naming](018-event-api-naming.md), [025 Interruptible Agent Steps](025-interruptible-agent-steps.md), [034 ACP-aligned Wire Tool Statuses](034-acp-aligned-wire-tool-statuses.md), [GitHub issue #902](https://github.com/openonion/connectonion/issues/902)

## Context

`co ai` could already delegate one task to Claude Code and resume the returned
session, but the adapter waited for one final JSON result. In O Chat this looked
like a long-running opaque tool call. Users could not see whether Claude was
reading a file, editing it, or running a command.

The product goal is narrower than exposing ConnectOnion as an ACP service:
`co ai` remains the parent agent, calls Claude Code as one tool, and shows
Claude's inner tool activity in the existing web experience. Public ACP ingress
and third-party clients are separate protocol work.

## Decision

The `claude_code` tool launches the installed Claude Code CLI with its
documented `--output-format stream-json --verbose` contract. It reads stdout
and stderr concurrently, parses newline-delimited events, and returns the same
stable final JSON envelope as before.

Claude `tool_use` blocks are translated to native `tool_call` IO events, and
matching `tool_result` blocks become native `tool_result` events. Wire IDs are
namespaced with `claude:`. Display names are prefixed with `Claude Code ›` so a
flat client remains understandable. Events also carry provider, child session,
and parent tool-use metadata without requiring current clients to understand
nested agents.

Arguments and results are bounded before live delivery. Common secret-shaped
argument keys are redacted. Duplicate starts are ignored, and an out-of-order
result receives a synthetic start so every result has a stable correlation
target under DD-034.

Cancellation and timeout remain owned by the parent tool call. The adapter
checks cancellation while the stream is quiet, terminates the provider process
group, closes inherited pipes, and relies on the parent interruptible IO lease
to reject late events.

Claude's intermediate text is not copied into the parent transcript. The
parent ConnectOnion agent remains responsible for the final response, review,
and claim of completion.

## Permission boundary

Permission mode remains operator-owned and absent from the model-visible tool
schema. Safe, Accept Edits, and explicit YOLO/ULW modes continue to bind a
Claude mode before launch; `bypassPermissions` is never selected by `co ai`.

This decision adds observability, not an approval bridge. Headless Claude Code
can execute actions allowed by its bound mode and local settings, but an
unmatched interactive permission request cannot round-trip through O Chat in
this version and fails closed.

## Why the CLI stream instead of the Python Agent SDK

At the decision date, `claude-agent-sdk` 0.2.136 requires Python `mcp>=1.23,<2`,
while ConnectOnion 1.7 requires `mcp>=2,<3`. Installing both in the same Python
environment is unsatisfiable. Weakening ConnectOnion's MCP v2 boundary to gain
one provider callback would create a framework-wide regression.

The CLI stream is Claude Code's documented automation interface, preserves the
user's installed authentication and `CLAUDE.md` behavior, and exposes the tool
events needed for the first product slice without another Python dependency.

Revisit the Agent SDK or an isolated sidecar when it is compatible with MCP v2,
or when a separately versioned bridge can support interactive permission
callbacks without sharing ConnectOnion's dependency environment.

## Rejected alternatives

- **Wait only for final JSON:** preserves the old opaque web experience.
- **Treat Claude Code as ACP ingress:** reverses the immediate client/agent goal
  and does not make the existing `co ai` delegation visible.
- **Install the Python Agent SDK beside MCP v2:** has an unsatisfiable declared
  dependency set at this decision date.
- **Lower ConnectOnion to MCP v1:** breaks the chosen 1.7 protocol baseline.
- **Forward all Claude text into the parent transcript:** creates two competing
  authors and unstable message ownership.
- **Claim live approval from tool events:** observability is not permission
  authority; unmatched prompts still need a real request/response bridge.

## Rollback

Return the CLI output format to final JSON and stop emitting provider events.
The public function signature, permission binding, session IDs, and final
result envelope do not need to change, so rollback does not require a data
migration.
