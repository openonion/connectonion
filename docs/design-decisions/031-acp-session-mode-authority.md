# DD-031: ACP session modes stay below launch authority

**Status:** Accepted

**Date:** 2026-08-10

## Context

ACP can advertise session modes and lets a client request `session/set_mode`.
ConnectOnion already persists `safe`, `accept_edits`, and `ulw` in the Agent
session. Those values are security policy, not presentation preferences:
`accept_edits` skips file-edit approval and `ulw` skips every tool approval for
a bounded number of autonomous turns.

The ACP client owns the user interface, but it must not gain more authority
than the operator granted when starting `co ai --acp`. Mode changes must also
share the persistent ownership and rollback boundary from DD-029 and the
approval boundary from DD-030.

## Decision

### Keep the existing session vocabulary

ACP IDs are the persisted ConnectOnion IDs:

- `safe`, displayed as **Safe**
- `accept_edits`, displayed as **Auto**
- `ulw`, displayed as **ULW**

The adapter does not translate a second set of mode names. New sessions store
an explicit mode, and new/resumed responses return the official
`SessionModeState`.

### Treat process launch as the authority ceiling

Safe and Auto are available to a local stdio client. ULW is advertised and
accepted only if the server was started with `--yolo`. A saved ULW session
cannot be resumed by a server without that launch authority. Its saved
remaining autonomous turns must also be no greater than this process's
`--yolo-turns` ceiling.

ULW state is valid only when all three bounded fields agree with `mode=ulw`:
`skip_tool_approval=true`, a positive `ulw_turns`, and a non-negative
`ulw_turns_used` below that limit. Safe or Auto snapshots containing ULW bypass
state are rejected. Unknown and malformed persisted modes fail closed before
the Agent can run.

The normal `enable_yolo` hook is disarmed after ACP constructs the runtime.
ACP's validated snapshot is the current mode; the launch flag only controls
whether that snapshot may enter ULW. This prevents a deliberate downgrade to
Safe or Auto from being silently reversed on the next prompt.

### Change mode only at an idle transaction boundary

`session/set_mode` and `session/prompt` use the same per-session lock. A busy
session rejects a mode request, so policy cannot change between a model
decision, approval request, and tool execution.

An idle change is prepared in a detached copy and written with the existing
atomic snapshot replacement. Only after that succeeds do the live Agent,
last-good checkpoint, and first-prompt resume copy observe the new mode. A
failed write exposes no partial in-memory grant. Cancellation and close wait
for an owned write to settle before the runtime or lease can be released.

### Use ACP's ordered update for internal changes

An Agent-originated `mode_changed` event maps to ACP
`CurrentModeUpdate(sessionUpdate="current_mode_update")` in the same ordered
generation stream as tool and message updates. The adapter defers that one
state notification until the prompt snapshot commits, so a failed save cannot
announce a mode that was rolled back. If notification delivery then fails, the
durable state remains authoritative and disk is never rolled back after the
commit point. The live runtime is quarantined and its lease released so it
cannot execute another prompt under stale client policy; reconnect/resume
re-advertises the durable mode. Unknown internal mode IDs abort the prompt and
its checkpoint instead of being announced as usable policy.

## Consequences

- An ACP UI can present and persist Safe/Auto without a parallel policy model.
- ULW remains an operator-granted capability; a client request or stored file
  cannot manufacture it.
- Mode changes may return “Session is busy” and be retried after the prompt.
- Older snapshots without a mode normalize to Safe. Corrupt or over-authorized
  snapshots require an explicit operator decision instead of silent repair.

## Rejected alternatives

- **Always advertise ULW:** lets a client escalate beyond process launch.
- **Silently downgrade saved ULW to Safe:** hides a material policy change and
  rewrites the meaning of a resumable session.
- **Change mode during a prompt:** creates a race at the approval boundary.
- **Mutate memory before saving:** can leave the runtime more permissive than
  the durable checkpoint after a disk failure.
- **Use adapter-only mode names:** creates translation and migration work with
  no security or usability benefit.

## Related decisions

- DD-019: Agent lifecycle and session-owned mode state
- DD-023: Trust and policy boundaries
- DD-025: Interruptible Agent steps
- DD-028: Ordered ACP event generations
- DD-029: Persistent ACP session ownership
- DD-030: Generation-scoped ACP tool approvals
