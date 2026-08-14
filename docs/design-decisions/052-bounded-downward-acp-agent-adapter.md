# DD-052: Downward ACP adapters expose bounded child activity

**Status:** Accepted

**Date:** 2026-08-13

## Context

ConnectOnion can act as an ACP client and delegate a coding task to Claude
Code, Codex, Gemini CLI, or another ACP agent. This is a downward adapter: the
child is an agent, while the outer ConnectOnion Agent remains responsible for
the user-visible session, permissions, persistence, and browser transport.
DD-043's native Claude Code activity stream remains the preferred first
product slice; this generic edge is an interoperability option, not its release
gate.

Equal protocol field names do not imply equal authority or privacy. DD-041
permits Host thoughts only when ConnectOnion persisted application text with
known provenance. DD-042 makes the outer plan a complete replacement owned by
the persisted TodoList. An arbitrary child ACP agent controls neither boundary.

Permission labels also need behavioral evidence. A real test of pinned
`codex-acp@1.1.14` showed that its `read-only` mode uses Codex
`approvalPolicy=on-request`: under ConnectOnion `deny`, the child executed
`curl` and reached the network without sending `session/request_permission`.
The native ConnectOnion Codex tool can request the stricter `untrusted` policy,
but the adapter's fixed ACP modes cannot.

## Decision

The generic `acp_agent` tool uses the pinned official Python ACP client and
exact-version Claude, Codex, and Gemini CLI commands. Gemini uses
`@google/gemini-cli@0.55.1` through its current native `--acp` route rather
than an operator's potentially stale global binary. A model may select a named
engine. Custom argv, approval policy, and workspace root exist only on an
operator-created `ACPAgent` instance; the public tool schema cannot supply
them.

Only the final `agent_message_chunk` text and bounded tool lifecycle metadata
cross the downward edge. Tool IDs and titles retain correlation, but ordinary
progress events omit `rawInput` and `rawOutput`. A manual permission card gets
one bounded JSON input preview so the operator can make an informed decision.
When an agent starts a new ACP `messageId`, the client discards text from the
previous message, such as a startup notice, so the result envelope contains the
final message rather than a concatenated transcript. Oversized message IDs are
reduced to the same stable bounded identifiers used for tool correlation.
The final message is capped at 64 KiB, errors at 4 KiB, event text at 512 bytes,
and one prompt emits at most 2,048 child events. Oversized IDs become stable
SHA-256-based IDs.

Child `agent_thought_chunk` and `plan` updates are not published as outer
`thinking` or `plan` events. A third-party thought may contain private model
reasoning. A child plan is not ConnectOnion's canonical TodoList replacement.
Nested child transcripts or plans require a later native event contract with
explicit parent identity, privacy, replay, and rendering semantics.

Named Claude sessions ignore persistent interactive CLI allow rules and
explicitly select Manual, Auto, or Don't Ask through advertised ACP session
modes. Gemini likewise must advertise the required mode. Missing modes fail
closed. After `initialize`, the generic client requires the agent-selected
protocol version to be a JSON integer equal to the v1 major it implements. It
observes the raw response correlated to the actual initialize request ID so a
schema library cannot quietly coerce `"1"` or `true` into version 1. An invalid
type or unsupported selection closes the child before any session lifecycle
request. For a supplied session ID, the generic client prefers an advertised
`sessionCapabilities.resume` because it needs continuation without transcript
replay. It retains `loadSession` as the compatibility path when resume is not
advertised. Once one method is selected, its failure is final: the client does
not try the other lifecycle method or silently create a fresh session. Claude
and Codex continuation reapply the same permission policy on either path. The
typed schema permits `agentCapabilities: null`; the client treats that as an
empty capability set and fails continuation before a lifecycle request instead
of leaking an internal attribute error or guessing an unsupported method.

Gemini CLI 0.55.1 advertises `session/load`, but real new-process conformance
testing could not load the session created by the preceding process. The named
Gemini route is therefore explicitly one-turn: it returns no resumable session
ID and rejects a supplied `session_id` before process launch. A future exact
pin may enable resume only after the same cross-process test passes; advertised
capability alone is insufficient.

[Google then stopped serving Gemini CLI requests](https://github.com/google-gemini/gemini-cli/discussions/28017)
for free, Pro, and Ultra individual OAuth accounts on June 18, 2026. An
exact-head rerun received the provider's explicit retirement response while the
same Claude and Codex tests passed. The Gemini route remains available only for
Google's supported API-key, Vertex, and enterprise Code Assist paths. A legacy
OAuth file is no longer a readiness signal, and Antigravity is not substituted
until it exposes a documented ACP entry point that passes the same version,
permission, environment, and real-provider review.

The subprocess starts from the ACP SDK's trimmed HOME, PATH, and shell
environment rather than inheriting every ambient secret. A named Claude child
adds only an explicitly configured `CLAUDE_CONFIG_DIR` or
`ANTHROPIC_API_KEY`; a named Codex child adds only its selected API key or
`CODEX_HOME`. A named Gemini child adds only the documented Gemini API-key or
Vertex authentication variables explicitly present in the operator
environment and disables browser launch. Stale or missing credentials fail the
turn instead of turning a child task into an interactive login flow. Unrelated
environment credentials do not cross this edge.

Named Codex ACP sessions have a narrower contract at the pinned adapter
version: only an operator-selected `auto` policy may launch. `manual` and
`deny` return an error before the process is spawned because the adapter cannot
enforce them for shell and outbound network actions. Ordinary callers use the
native `codex` tool instead. `engine_status()` publishes this limitation as
`supported_approval_modes=["auto"]`; launcher or credential-file presence is
never presented as proof of a valid or safe provider session.

`co ai` registers a thin wrapper rather than the raw operator constructor. Read
only and Workspace permission profiles select `manual`; only a valid, bounded
Full Access grant selects `auto`. Hosted non-admin requesters cannot launch a
local ACP child. The wrapper receives the same explicit local-session grant as
the native coding wrappers, but that grant never enters shared remote EXEC
configuration.

Manual approval waits on a revocable per-tool IO lease and remains inside the
turn's total deadline. Timeout or interruption revokes the lease so a pending
approval cannot leave the ACP subprocess alive. The client may select only an
`allow_once` response; it never converts one prompt into a persistent rule.

The child process uses ConnectOnion's strict ACP stdio transport before the
pinned SDK client router. The SDK otherwise promotes `_meta` entries over typed
callback arguments after validation. Metadata cannot therefore replace the
visible `sessionId`, permission options, tool call, or update delivered to
`ToolClient`; shadowed requests receive `InvalidParams`, and shadowed
notifications are dropped. Unrelated metadata remains an ACP extension and is
not interpreted as authority.

That shared guard also derives top-level callback wire keys from the pinned
models. A child must send `sessionId` and `toolCall`, not the Python-only
`session_id` or `tool_call` names that generated models accept for local
construction. Non-schema root fields are rejected; opaque `_meta`, nested ACP
validation, optional/null values, and underscore extension methods remain
owned by the official protocol layers.

The operator also binds a launch workspace root. Model-selected `cwd` values
may choose only that directory or a resolved descendant; symlink escapes fail
closed. This constrains working-directory selection, not every engine's
filesystem syscalls. Strong hostile-code containment still requires an
operator-provided container or OS sandbox. Custom ACP commands cannot promise
engine-specific mode enforcement and remain an advanced operator-owned edge.
The convenience function resolves this root at call time from the Agent's
operator-bound delegation workspace, or the current directory when no Agent is
present; it does not retain an import-time working directory as a wider root.

## Consequences

- Claude Code, Codex, and Gemini share one typed protocol client without
  replacing the preferred native Claude/Codex tools.
- A resume-only ACP agent can continue a session, while load-only adapters keep
  their proven compatibility path and agents advertising both avoid replaying
  history the outer tool will discard.
- An agent selecting an unsupported protocol major cannot receive a v1 session
  or prompt request after initialization.
- Browser tool cards show bounded child activity without copying arbitrary
  command arguments, file contents, provider output, thoughts, or plans.
- The generic Codex ACP route remains available for explicit Full Access, while
  normal approval-aware delegation fails closed onto the native Codex route.
- Gemini remains useful for bounded one-turn delegation without exposing an
  ephemeral process-local ID as durable state.
- A timed-out approval is revoked with the same child turn instead of leaving
  a blocked worker or live subprocess behind.
- A child cannot use `_meta` to make the session or permission callback checked
  by `ToolClient` disagree with its visible ACP fields.
- A child cannot reach `ToolClient` through a Python-specific wire alias or an
  ignored custom root parameter.
- Re-enabling Codex `manual` or `deny` requires a pinned adapter plus a real
  conformance test covering file writes, shell commands, and outbound network.

## Rejected alternatives

- **Describe `read-only` as manual approval despite real behavior:** creates a
  false security promise and leaves an unapproved network path.
- **Forward every ACP update into the same-named native event:** confuses child
  state with authoritative outer state and can disclose private reasoning.
- **Inherit interactive Claude/Codex configuration:** persistent allow rules or
  approval reviewers can bypass the current ACP client.
- **Expose command or approval as model arguments:** lets the model select local
  process execution or weaken policy.
- **Use unpinned `npx` packages:** executes unreviewed adapter updates.
- **Silently start a new session after resume failure:** loses continuity while
  falsely reporting successful delegation.
- **Require `session/load` for every continuation:** rejects agents that expose
  the narrower ACP `session/resume` capability and asks dual-capability agents
  to replay history that this adapter deliberately does not consume.
- **Retry through the other lifecycle method after a request failure:** can
  duplicate accepted work and hides the selected continuation contract.
- **Keep sending v1 messages after an agent selects another major:** confuses a
  well-typed version value with an agreed protocol and can execute under the
  wrong wire semantics.
- **Trust only the SDK's coerced protocol-version field:** accepts strings and
  booleans as v1. Making every ACP model globally strict or copying the full
  initialize schema would widen this focused compatibility fix unnecessarily.
- **Reject or guess around a null agent capability object:** the pinned schema
  permits null. Treating it as no optional capabilities preserves negotiation;
  blindly trying a lifecycle method does not.

## Related decisions

- DD-024: subagent system design
- DD-032: ACP interoperability evidence
- DD-041: public ACP Host thoughts
- DD-042: stable ACP session plans
- DD-043: Claude Code live tool events
- DD-044: canonical approval and permission-profile vocabulary
- DD-051: explicit ACP state isolation
