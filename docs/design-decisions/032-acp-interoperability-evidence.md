# DD-032: ACP interoperability needs typed and framing evidence

**Status:** Accepted

**Date:** 2026-08-10

## Context

The ACP adapter already has direct unit tests and raw JSON-RPC subprocess
tests. Those tests can prove ConnectOnion behavior and newline-delimited stdio
framing, but project-owned dictionaries cannot prove that an independent ACP
implementation accepts the messages.

ACP also distinguishes clients from agents. ConnectOnion, Claude Code, and
Codex are agents. Editors such as Zed and JetBrains are clients that launch an
agent subprocess. Compatibility documentation must not present one peer agent
as the host for another.

## Decision

### Keep two complementary CI boundaries

Raw subprocess tests continue to own transport properties that an SDK hides:
stdout contains protocol frames only, large frames are not truncated, EOF
settles work, and retired generations cannot leak output.

A second subprocess suite uses the official Python ACP client API to launch a
deterministic fixture that calls the production `serve_acp` stdio adapter. The
official client models validate requests, responses, notifications, modes, and
permission callbacks while they cross the real stdio boundary. Only the
model-backed coding Agent is replaced; the ACP router and server remain
production code.

Both suites are isolated from user state, credentials, and the network. Client
permission callbacks reject by default.

The pinned Python SDK expands request `_meta` entries into handler keyword
arguments. Every ConnectOnion-owned router therefore uses the same narrow
pre-router rule: a metadata key cannot use the generated Python name of an
official request or implemented callback field and replace that field after
validation. Native stdio/WebSocket apply it before Agent routing; the generic
`acp_agent` child process uses the shared strict stdio transport before
`ToolClient` callback routing. Other metadata remains untouched. The same
pinned-model registry derives each routed method's top-level wire names from
explicit Pydantic aliases. This keeps Python construction names such as
`session_id` and `mode_id` from becoming a second ACP dialect, and rejects
custom root fields that ACP requires callers to place under `_meta`. Requests
with either violation receive `InvalidParams`; invalid notifications are
dropped without a response. Nested values, types, nullability, enums, and
results remain validated by the official SDK rather than a copied
ConnectOnion schema.

### State the tested version contract

The package supports `agent-client-protocol>=0.12.0,<0.13.0` and negotiates
ACP `protocolVersion=1`. Compatibility claims name that range instead of the
unbounded phrase “ACP compatible.” A future SDK-minor upgrade must update the
bound and rerun both test layers before the table changes.

### Separate automated conformance from editor smoke paths

Zed and JetBrains receive copy-paste custom-agent configurations that run
`co ai --acp` in the selected project. CI validates the same production stdio
adapter through the official client SDK; CLI argument wiring remains a separate
test boundary. We do not claim that a GUI editor binary runs in CI;
editor-specific installation and UI behavior remain documented smoke paths
until a stable headless host runner exists.

Claude Code and Codex may be listed as peer ACP agents for orientation, but not
as clients that launch ConnectOnion.

## Consequences

- Schema or router drift fails in the official SDK client before release.
- Raw clients cannot use `_meta` to make executed handler arguments disagree
  with the visible request fields.
- Raw clients must use the pinned ACP wire aliases for routed top-level params;
  Python SDK field names are never accepted as protocol spellings.
- Framing regressions remain visible instead of being hidden by SDK helpers.
- Interoperability claims say exactly which layer and version were exercised.
- The deterministic fixture is shared by raw and typed subprocess suites.
- GUI integration can still change independently and must not be overstated.

## Rejected alternatives

- **Only raw JSON fixtures:** validates our expectations against themselves.
- **Only the official SDK client:** hides stdout pollution and framing details.
- **Copy ACP schemas into tests:** creates a second protocol implementation to
  maintain.
- **Install a desktop IDE in the normal test matrix:** slow, brittle, and not a
  reliable headless contract.
- **Call Claude Code or Codex a host:** reverses the ACP client/agent roles.

## Related decisions

- DD-028: Ordered ACP event generations
- DD-029: Persistent ACP session ownership
- DD-030: Generation-scoped ACP tool approvals
- DD-031: ACP session mode authority
