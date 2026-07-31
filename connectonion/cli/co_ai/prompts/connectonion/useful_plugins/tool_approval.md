# tool_approval

Ask the user before a tool call that can change something, and remember the
answer for as long as the answer should last.

## Modes

The plugin is the same in every mode; what moves is the gate.

| mode | behaviour |
|---|---|
| `safe` | dangerous tool calls are confirmed one at a time |
| `plan` | the agent proposes a plan and waits for review before doing anything |
| `accept_edits` | file edits land without asking; other dangerous calls still ask |
| `ulw` | runs unattended for a bounded number of turns — see `useful_plugins/ulw` |

Mode changes arrive over the WebSocket, so a client can move between them
mid-session without restarting the agent.

## Scope of an approval

An approval can be granted **once** or **for the session**. Session-scoped
approvals are held in the session's permission state, which is why a skill's
temporary grants are snapshotted and restored around the skill rather than
merged into it — a permission the user gave for one turn must not survive
into the next.

## What it does not do

It does not decide what is dangerous. That comes from the tool's own
declaration and the permission patterns, so adding a tool does not mean editing
this plugin.
