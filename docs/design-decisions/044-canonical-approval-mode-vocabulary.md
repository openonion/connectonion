# DD-044: One permission-mode contract

**Status:** Accepted

**Date:** 2026-08-21

**Related:** [Issue #1142](https://github.com/openonion/connectonion/issues/1142),
[Issue #1140](https://github.com/openonion/connectonion/issues/1140),
[053 One browser protocol, native coding adapters](053-oip-only-browser-and-native-coding-adapters.md)

## Context

The 1.7 preview mixed collaboration state, permission policy, provider-private
settings, and autonomous continuation in one selector. Core, Host/OIP, React,
O Chat, Codex, and Claude Code consequently used overlapping vocabularies and
could disagree about which component held authority.

Plan Mode also conflated planning with permission. A Todo List is useful
progress data, but neither planning nor a completed todo may authorize a tool.
Likewise, Full access is a bounded permission grant; it is not an instruction
to continue generating Agent turns.

## Decision

ConnectOnion 1.7 has exactly three public permission modes:

| Canonical ID | Display name | Meaning |
|---|---|---|
| `read-only` | Read only | Reads may run; every effectful operation asks. |
| `auto` | Auto | The default. Deterministic policy allows safe reversible workspace work and asks or denies higher-risk work. |
| `full-access` | Full access | Routine approvals are skipped for a positive, bounded number of user-driven turns. |

Core owns the authoritative state:

```python
{"mode": "read-only" | "auto" | "full-access", "turns_left": int | None}
```

`turns_left` exists only for Full access. Completing a user-driven Agent turn
decrements it; zero atomically returns the mode to Auto. The public state does
not cache derived authority such as `skip_tool_approval`, and it does not keep
total/used counter pairs that can disagree.

`connectonion/core/mode.py` defines the IDs, validation, safe reads, the only
writer, approval-bypass derivation, and countdown transition. Host/OIP and
provider lifecycle events use the same IDs. Provider-private values are
translated only inside their adapters and never appear in public events or
persisted session state.

Every new session starts in Auto regardless of whether the participant is a
local operator, administrator, invited user, or contact. Administrative
control-plane authorization remains separate from ordinary session mode.

Plan is not a permission mode. Plan-mode protocol fields, permission behavior,
UI controls, and prompts are removed. Todo List remains ordinary
`pending` / `in_progress` / `completed` progress data with no authority.

`--yolo` may remain a CLI convenience that selects bounded Full access. Full
access never synthesizes a follow-up prompt or recursively calls
`agent.input(...)`. Structured continue-until-complete execution belongs to the
separate Goal plugin planned for 1.9.

## Compatibility

There is no legacy vocabulary compatibility layer in 1.7. The following are
not accepted, translated, emitted, persisted, documented as modes, or tested
as supported values:

```text
:read-only  :workspace  :danger-full-access
safe  default  manual  accept_edits  auto_approve
ulw  full_access  plan  planning
```

An old, unknown, or incomplete stored value is discarded at the 1.7 schema
boundary and initialized to Auto. It is never translated into authority. A
Full access label without a valid positive countdown cannot skip approval.

This intentional contract correction requires coordinated Core, React, and O
Chat releases. The exact package versions and shared fixture SHA are recorded
in the 1.7 release-control issue before a Beta or RC is promoted.

## Consequences

- one state owner replaces compatibility aliases and duplicated authority;
- reconnect and replay carry the same three IDs as live requests;
- frontend labels and backend values cannot drift;
- Full access expiry is deterministic and bounded;
- Todo List and planning remain useful without becoming authorization;
- rolling old/new combinations fail safely instead of entering reconnect loops
  or guessing authority.

## Release evidence

1. Focused Core mode and policy unit tests.
2. Host transaction, reconnect, replay, and invalid-state fixtures.
3. Real Codex and Claude Code permission/Stop/resume smokes.
4. React typecheck, unit tests, build, and packed-artifact audit.
5. O Chat desktop and 320–390 px mode-control journeys.
6. A clean wheel plus exact published React prerelease in O Chat.
7. Direct and Relay old/new pair tests proving safe failure and rollback.

## Rejected alternatives

- **Keep Codex colon-prefixed profiles as the public contract:** leaks one
  provider's vocabulary into every client and does not match the product IDs.
- **Retain legacy aliases for rolling compatibility:** prolongs multiple
  authorities; the release decision is one synchronized vocabulary.
- **Keep Plan as a fourth mode:** confuses workflow progress with permission.
- **Make Full access mean continue until completion:** combines approval with
  execution control and permits runaway work.
- **Role-specific ordinary defaults:** makes identical user actions receive
  different permission semantics; control-plane roles are handled separately.
