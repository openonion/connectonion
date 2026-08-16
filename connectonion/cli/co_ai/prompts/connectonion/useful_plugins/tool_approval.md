# tool_approval

Ask the user before a tool call that can change something, and remember the
answer for as long as the answer should last.

## Modes

The plugin is the same in every mode; what moves is the gate.

| mode | behaviour |
|---|---|
| `:read-only` (legacy `default`/`safe`) | every unpermitted live-IO call asks an authenticated user |
| `:workspace` (legacy `auto_approve`/`accept_edits`) | deterministic Auto permits workspace reads, reversible edits, and focused verification; higher-impact calls ask or deny |
| `:danger-full-access` (legacy `full_access`/`ulw`/`yolo`) | explicit, Host-bounded bypass — see `useful_plugins/full_access` |
| `plan` | workflow state; it does not grant a permission profile |

Mode changes arrive over the WebSocket, so a client can move between them
mid-session without restarting the agent. In a hosted session, only the admin
operator can enable Auto or Full access; authenticated contacts can still
answer their own manual approval requests.

## Scope of an approval

An approval can be granted **once** or **for the session**. Session-scoped
approvals are held in the session's permission state, which is why a skill's
temporary grants are snapshotted and restored around the skill rather than
merged into it — a permission the user gave for one turn must not survive
into the next.

## Classification boundary

The Auto policy is a narrow allowlist: workspace reads, reversible edits, and
focused test/lint/build commands can proceed. Unknown or external calls ask;
credential access, deletion, control-file writes, and writes outside the
workspace are denied. An Auto `ask` cannot be overridden by a broad template,
config, or skill rule; only a prior human session grant can reuse it.

The co ai `codex` and `claude_code` wrappers receive explicit grants only inside
the outer LLM-loop session because their inner runtimes own action approval.
That scope applies to CLI and hosted co-ai sessions, but the grants never enter
the shared remote-EXEC whitelist. Hosted non-admin Claude delegation is refused;
hosted non-admin Codex is read-only with nested approvals denied.
