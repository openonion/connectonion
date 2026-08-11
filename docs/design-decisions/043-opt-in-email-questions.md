# DD-043: Keep Unattended Email Questions Opt-In and Non-Secret

**Status:** Accepted  
**Date:** 2026-08-12  
**Related:** [Fail Closed for Unclassified Tools](fail-closed-unclassified-tools.md), [030 Generation-scoped Tool Approvals](030-acp-generation-scoped-tool-approvals.md), [037 Bound ACP Host Permissions](037-bound-acp-host-permissions.md)

## Context

`ask_user` can reach a live browser through `agent.io`, but a one-shot, cron,
or deployed run may have no connected human. Email is already available to an
agent, so it is a useful delayed contact channel. It is also an outward side
effect, a persistent store, and a weak substitute for the authenticated,
session-bound approval protocol. Making it automatic merely because
`OWNER_EMAIL` exists would change a local no-IO call from an immediate result
into a send plus a fifteen-minute block.

A fixed recent-message poll is not reliable: enough unrelated messages can
push the correlated reply outside the window forever. Sender address alone is
also insufficient because unrelated and concurrent owner messages can cross.

## Decision

The live `agent.io` path remains authoritative and unchanged. Without live IO,
email is attempted only when `CONNECTONION_ASK_USER_EMAIL=1` is explicitly
configured. The timeout and polling interval are bounded. Waits check the
agent's cancellation state in short increments; each inbox request is capped
at two seconds and never receives a timeout longer than the remaining overall
deadline. A process permits only one pending question per owner with a
cooldown between attempts.

`OWNER_EMAIL` names the contact for ordinary `ask_user` answers. A value in the
machine-global `~/.co/keys.env` wins over a conflicting project-loaded value;
deployed applications may supply the contact in their process environment.
The response never satisfies Host or ACP tool permission. Those protocols keep
their authenticated admin, request, session, generation, and tool-call
bindings from DD-030 and DD-037.

Email fallback accepts only bounded, unique, non-sensitive choice questions
without free-form fields. Choices receive stable numeric IDs, and replies must
contain only those IDs; commas inside the human-readable labels are therefore
unambiguous. Each question receives a 128-bit `CO-ASK` subject tag. oo-api filters the
authenticated inbox by that literal tag before applying its result limit and
echoes the exact applied filter as a capability proof. The framework rejects
an old deployment that silently ignores the query parameter, then still
requires both the configured sender and exact tag. A matched reply is consumed
once and marked read; cleanup failure cannot resend the question or discard an
answer already received.

The outbound body is escaped into a small HTML wrapper because the backend
sends `body` as HTML. Subjects use only the first printable question line.
Password, secret, token, OTP, one-time-code, and verification-code questions,
fields, choices, and common secret-shaped values fail before email is sent:
received email is persistent, and a secret relay requires an explicit
retention/redaction design of its own. Pattern detection is defense in depth,
not a general secret classifier: callers opting into this channel remain
responsible for never supplying secret-bearing question or choice data.

Every failure remains `NOT ANSWERED` and explicitly not approval.

## Consequences

- Existing library and one-shot behavior does not acquire an implicit send or
  long wait.
- Compatible backends cannot hide a correctly tagged answer behind newer mail;
  older backends fail closed instead of pretending the filter was applied.
- Email can restore delayed human choices, but cannot become a second ACP/Host
  authorization engine.
- The original OTP-relay use case is intentionally deferred until a
  non-persistent or redacted secret channel exists.

## Rejected alternatives

- **Always email when `OWNER_EMAIL` is present:** configuration discovery would
  silently create an outward side effect and blocking behavior.
- **Poll a larger recent-message window:** any fixed window can still lose the
  reply and makes each poll more expensive.
- **Treat email as tool approval:** it lacks the authenticated session/request
  binding already enforced by Host and ACP.
- **Send password/OTP fields and mark the reply read:** read state is not
  deletion or redaction; the provider and backend still retain the body.
