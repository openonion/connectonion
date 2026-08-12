# DD-044: Downward ACP adapters expose bounded child activity

**Status:** Accepted

**Date:** 2026-08-12

## Context

ConnectOnion can act as an ACP client and delegate a coding task to Claude
Code, Codex, Gemini CLI, or another ACP agent. This is a downward adapter: the
child is an agent, while the outer ConnectOnion Agent remains responsible for
the user-visible session, permissions, persistence, and browser transport.
DD-043's native Claude Code activity stream is the first product slice; this
generic ACP adapter is a later interoperability edge and is not its release
gate.

ACP uses the same update names at both levels, but equal names do not mean equal
authority or privacy. DD-041 permits Host thoughts only when ConnectOnion
persisted application text with known provenance. DD-042 makes the outer plan a
complete replacement owned by the persisted TodoList. An arbitrary child ACP
agent controls neither boundary.

## Decision

The generic `acp_agent` tool uses the pinned official Python ACP client and
exact-version named adapter commands. A model may select a named engine. Custom
argv and approval policy exist only on an operator-created `ACPAgent` instance;
the public tool schema cannot supply them.

Only the final `agent_message_chunk` text and bounded tool lifecycle metadata
cross the downward edge. Tool IDs and titles retain correlation, but ordinary
progress events omit `rawInput` and `rawOutput`. A manual permission card gets
one bounded JSON input preview so the operator can make an informed decision.
The final message is capped at 64 KiB, errors at 4 KiB, event text at 512 bytes,
and one prompt emits at most 2,048 child events. Oversized IDs become stable
SHA-256-based IDs.

Child `agent_thought_chunk` and `plan` updates are not published as outer
`thinking` or `plan` events. A third-party thought may contain private model
reasoning. A child plan is not ConnectOnion's canonical TodoList replacement.
Nested child transcripts or plans require a later native event contract with
explicit parent identity, privacy, replay, and rendering semantics.

The operator-bound permission mode is an authority ceiling. Named Codex
sessions force the adapter's user approval reviewer and start at read-only for
manual or deny. Named Claude sessions ignore persistent interactive CLI allow
rules and explicitly select Manual or Don't Ask through ACP session modes.
Missing required modes fail closed. Resume reapplies the same policy and never
silently creates a fresh session after load failure.

Manual approval waits on a revocable per-tool IO lease and remains inside the
turn's total deadline. Timeout or interruption revokes the lease so a pending
approval cannot leave the ACP subprocess alive. The adapter can select only an
`allow_once` response; it never converts one prompt into a persistent rule.

The operator also binds a launch workspace root. Model-selected `cwd` values
may only choose that directory or a resolved descendant; symlink escapes fail
closed. This constrains working-directory selection, not every engine's
filesystem syscalls. Codex supplies its own sandbox; Claude Code and Gemini
enforce their advertised permission modes. Strong hostile-code containment
still requires an operator-provided container or OS sandbox.
Custom ACP commands cannot promise engine-specific mode enforcement, so they
still receive fail-closed permission callbacks but remain an advanced
operator-owned integration boundary.

## Consequences

- Claude Code and Codex share one typed protocol client without replacing their
  existing native tools.
- Browser tool cards show child activity without copying arbitrary command
  arguments, file contents, or provider output into progress events.
- A child cannot overwrite the outer session's thought or plan state merely by
  sending a protocol field with the same name.
- Operator refusal is enforced by the adapter session mode and ACP response,
  not just represented as a UI preference.
- A timed-out approval is revoked with the same child turn instead of leaving a
  blocked worker or live subprocess behind.
- Detailed nested child state remains unavailable until its native semantics
  are designed deliberately.

## Rejected alternatives

- **Forward every ACP update into the same-named native event:** confuses child
  state with authoritative outer state and can disclose private reasoning.
- **Inherit the user's Claude/Codex interactive configuration:** persistent
  allow rules or approval reviewers can bypass the current ACP client.
- **Expose command or approval as model arguments:** lets the model select local
  process execution or weaken policy.
- **Use unpinned `npx` packages:** executes unreviewed adapter updates.
- **Silently start a new session after resume failure:** loses continuity while
  falsely reporting successful delegation.

## Related decisions

- DD-024: subagent system design
- DD-032: ACP interoperability evidence
- DD-043: Claude Code live tool events
- DD-041: public ACP Host thoughts
- DD-042: stable ACP session plans
