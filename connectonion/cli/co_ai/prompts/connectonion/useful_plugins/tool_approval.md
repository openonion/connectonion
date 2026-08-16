# tool_approval

Ask the user before a tool call that can change something, and remember the
answer for as long as the answer should last.

## Modes

The plugin is the same in every mode; what moves is the gate.

| mode | behaviour |
|---|---|
| `default` | deterministic Auto Approve for workspace work; higher-impact calls ask or deny |
| `safe` | every call without an explicit permission asks |
| `full_access` | explicit local/Host-admin access, bounded by Host controls |

`accept_edits`, `ulw`, and `yolo` remain compatibility aliases. Plan is stored
as workflow state and does not change the approval profile.

Mode changes arrive over the WebSocket, so a client can move between them
mid-session without restarting the agent.

## Scope of an approval

An approval can be granted **once** or **for the session**. Session-scoped
approvals are held in the session's permission state, which is why a skill's
temporary grants are snapshotted and restored around the skill rather than
merged into it — a permission the user gave for one turn must not survive
into the next.

## Policy decisions

The Default policy emits a versioned `allow`, `ask`, or `deny` decision with a
reason, effect class, and scope. Unknown tools ask rather than running silently.
An `ask` reuses the same human approval protocol and permission state as before.
