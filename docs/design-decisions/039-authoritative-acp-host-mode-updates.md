# DD-039: Host mode updates report authority; they do not grant it

**Status:** Accepted

**Date:** 2026-08-11

## Context

DD-031 defines ACP session-mode authority for the local stdio adapter. The
authenticated network Host still reports an Agent's completed mode change only
as the ConnectOnion `mode_changed` event. The active browser path is Host →
`@connectonion/react` → O Chat; the standalone TypeScript SDK is retired.

The network carrier needs ACP-compatible output without turning a presentation
field into a permission grant or changing persisted sessions during rollout.

## Decision

The Host mirrors an Agent-originated `mode_changed` event as the exact ACP v1.19
`CurrentModeUpdate(sessionUpdate="current_mode_update")`. The persisted IDs are
used directly: `safe`, `accept_edits`, and `ulw`. `plan` is a legacy request
alias that the Agent normalizes to Safe; it is not valid authoritative output.

The Host-owned connection session ID is placed in the ACP notification. A
session ID supplied by the Agent event is never trusted. The ACP mirror is sent
immediately before the existing legacy event, preserving event order. Invalid
mode IDs skip the additive mirror without blocking the legacy stream or the
terminal `OUTPUT`; updated readers validate both representations and ignore the
invalid value.

This notification reports policy that the Agent has already applied. It cannot
change approval behavior, restore ULW, increase ULW turns, or bypass the
operator checks in the tool-approval hooks. Canonical traces and session
snapshots remain unchanged.

Client `mode_change` is not renamed to ACP `session/set_mode` in this slice.
That request needs its own transaction design covering an owned response,
available-mode advertisement, busy-session rejection, durable commit, and the
`--yolo` launch-authority ceiling from DD-031.

## Consequences

- React can consume one standard authoritative mode notification while O Chat
  stays protocol-free.
- New readers de-duplicate ACP plus legacy output; old readers keep working.
- Unknown modes cannot become more permissive by coercion.
- Rollback stops the additive mirror and does not rewrite stored data.

## Rejected alternatives

- **Treat `currentModeId` as authority:** a client-controlled field must not
  grant tool permissions.
- **Emit ACP only:** breaks released clients during a minor-version rollout.
- **Map `plan` as a persisted ACP mode:** preserves a UI alias the Agent does
  not actually enforce.
- **Migrate the setter at the same time:** combines observation with a durable,
  security-sensitive policy transaction.

## Related decisions

- DD-031: ACP session modes stay below launch authority
- DD-035: Versioned ACP Host carrier
- DD-037: Bound ACP Host permissions
- DD-038: Negotiated ACP Host cancellation

