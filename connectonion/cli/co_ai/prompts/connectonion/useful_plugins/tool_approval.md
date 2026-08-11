# tool_approval

Ask the user before a tool call that can change something, and remember the
answer for as long as the answer should last.

## Modes

The plugin is the same in every mode; what moves is the gate.

| mode | behaviour |
|---|---|
| `safe` | local/admin operators confirm each unpermitted tool; hosted non-admin requesters are rejected without a dialog |
| `plan` | legacy client request; normalized to `safe` |
| `accept_edits` | local/admin-only: named file edits land without asking; every other unpermitted call still needs operator approval |
| `ulw` | local/admin-only bounded approval bypass — see `useful_plugins/ulw` |

Mode changes arrive over the WebSocket, so a client can move between them
mid-session without restarting the agent. In a hosted session, only the admin
operator can enable `accept_edits` or `ulw`; other requesters remain in `safe`.

## Scope of an approval

An approval can be granted **once** or **for the session**. Session-scoped
approvals are held in the session's permission state, which is why a skill's
temporary grants are snapshotted and restored around the skill rather than
merged into it — a permission the user gave for one turn must not survive
into the next.

## Classification boundary

The approval boundary is an allowlist, not a denylist. Template, config, skill,
session, and explicit mode permissions run first. With live IO, every remaining
tool must receive operator approval; a hosted non-admin requester is rejected
without a dialog. Adding a plugin or MCP tool therefore cannot silently acquire
side effects just because its name is new.

The co ai `codex` and `claude_code` wrappers receive explicit grants only inside
the outer LLM-loop session because their inner runtimes own action approval.
That scope applies to CLI and hosted co-ai sessions, but the grants never enter
the shared remote-EXEC whitelist. Hosted non-admin Claude delegation is refused;
hosted non-admin Codex is read-only with nested approvals denied.
