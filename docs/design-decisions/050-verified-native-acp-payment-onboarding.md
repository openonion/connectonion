# DD-050: Verify payment inside native ACP browser admission

**Status:** Accepted

**Date:** 2026-08-13

**Related:** [DD-045 Authenticated ACP WebSocket Gateway](045-authenticated-acp-websocket-gateway.md), [Issue #928](https://github.com/openonion/connectonion/issues/928)

## Context

The native browser ACP gateway accepts a signed JSON body at
`POST /acp/authorize`. Public discovery can advertise invite-code and payment
onboarding, but the original admission path passed both fields only through
the normal trust decision. Invite codes work there. Payment deliberately does
not: a number written by the caller is not evidence of a transfer, so the fast
trust rules refuse to grant access from it.

Legacy `/ws` verifies payment in a later signed `ONBOARD_SUBMIT` frame. React
cannot use that path after native ACP was selected without creating an
error-driven downgrade and a second transport lifecycle.

## Decision

Native payment onboarding completes inside the existing signed authorization
exchange. After exact signature, recipient, Origin, request-body digest, and
one-use request-ID verification, the Host rate-limits the verified principal.
Rejected attempts consume the same bounded admission budget as successful
ones, before trust evaluation or payment-provider work.

The ordinary trust decision runs first. If it refuses and the signed request
contains a positive payment claim, the Host calls the existing
`TrustAgent.verify_payment()` outside the ASGI event loop. That verifier, not
the caller's number, resolves the operator-configured minimum and confirms a
recent transfer from the authenticated caller to the Host's own address. It
promotes the caller only after verification. A successful admission then
issues the normal origin-bound, one-use browser ticket.

Verification refusal returns the same generic trust error. Provider failures
fail closed without exposing provider details. Blocked, malformed, replayed,
wrong-recipient, wrong-Origin, and rate-limited requests never reach payment
verification. Every gateway response, including a refusal, is `no-store` so a
completed onboarding cannot remain hidden behind a cached denial. React never
opens `/ws` to finish native onboarding.

The payment recipient displayed by React is the requested Agent address. The
same address must match `/info.address` during transport discovery and is the
Host identity used by the payment verifier, so no second public identity field
is introduced.

## Rejected alternatives

- **Trust the signed `payment` number:** signatures prove who made a claim, not
  that money moved. This would restore the historical pay-nothing bypass.
- **Open legacy `/ws` for `ONBOARD_SUBMIT`:** native selection would no longer
  be atomic and failures could create duplicate connections or prompts.
- **Run payment verification on the ASGI loop:** provider timeouts would stall
  unrelated ACP connections.
- **Rate-limit only successful tickets:** rejected callers could create
  unbounded trust and external-verification work.
- **Publish a separate payment address:** the public Agent identity already is
  the verified recipient; another field could drift from it.

## Compatibility and rollback

Invite onboarding and already-trusted callers are unchanged. Removing this
slice makes payment-only native onboarding fail closed again; it does not
weaken admission or redirect the client to legacy transport.
