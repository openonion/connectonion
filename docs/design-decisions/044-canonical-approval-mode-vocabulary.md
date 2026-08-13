# DD-044: Align collaboration and permissions with Codex

**Status:** Accepted

**Date:** 2026-08-12

**Related:** [031 Session Mode Authority](031-acp-session-mode-authority.md), [039 Authoritative Host Mode Updates](039-authoritative-acp-host-mode-updates.md), [040 Durable Host Mode Transactions](040-durable-acp-host-session-mode-transactions.md), [Issue #903](https://github.com/openonion/connectonion/issues/903)

## Context

ConnectOnion historically mixed `safe`, `plan`, and `ulw` in one selector.
That combined two different questions: how the agent collaborates with the
user, and what the agent may do without asking. It also required
ConnectOnion-specific vocabulary across Host, React, O Chat, and delegated
coding tools.

Codex keeps those concerns independent. Its app-server collaboration mode has
`default` and `plan`; its built-in permission profiles are `:read-only`,
`:workspace`, and `:danger-full-access`.

## Decision

Connect uses the same two-layer model:

| Layer | Canonical ID | Display name |
|---|---|---|
| Collaboration | `default` | Default |
| Collaboration | `plan` | Plan |
| Permission | `:read-only` | Read only |
| Permission | `:workspace` | Auto |
| Permission | `:danger-full-access` | Full access |

Collaboration is client workflow state. Plan never grants or rewrites Host
authority. Permission profiles are authenticated Host state and change only
after the durable ACP `session/set_mode` transaction is acknowledged.

`Auto` is the product label for the workspace profile, not a canonical
`auto_approve` identifier. `--yolo` remains a recognizable CLI shorthand for
Full access; it is not a fourth mode or the primary UI/code identifier.

The exact permission profiles are emitted on ACP and persisted in session
state. Full access remains operator-only and requires ConnectOnion's complete,
current Host grant and turn ceiling. This vocabulary alignment does not claim
that every provider implements Codex's operating-system sandbox.

Provider adapters translate the permission profile at their boundary. Codex
receives `read-only`, `workspace-write`, or `danger-full-access`; Claude Code
receives its own provider-specific permission value. Those terms do not leak
back into Connect's public contract.

## Migration

Compatibility readers accept old persisted or wire values only at the
boundary, normalize immediately, and never newly emit them:

| Previous value | Canonical result |
|---|---|
| `safe`, `default` | `:read-only` |
| `accept_edits`, `auto_approve` | `:workspace` |
| `ulw`, `full_access` | `:danger-full-access` |
| `plan` in an old permission field | collaboration `plan` plus permission `:read-only` |

Unknown or incomplete authority fails closed. A malformed Full access label
without its bounded grant is downgraded before any tool can run.

## References

- [Codex agent approvals and security](https://learn.chatgpt.com/codex/agent-approvals-security)
- [Codex permissions](https://learn.chatgpt.com/codex/permissions)
- [Codex configuration reference](https://learn.chatgpt.com/codex/config-file/config-reference)

## Rejected alternatives

- **One selector containing Plan and Full access:** still conflates workflow
  intent with authority.
- **Public `auto_approve` / `full_access` IDs:** resembles common wording but
  does not match Codex's profile contract.
- **YOLO as a fourth protocol value:** duplicates Full access and complicates
  every client.
- **Silent unknown-value fallback in Host authority:** can hide corrupt or
  over-authorized persisted state.
