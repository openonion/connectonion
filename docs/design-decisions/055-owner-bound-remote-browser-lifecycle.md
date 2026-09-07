# DD-055: Remote Browser starts with owner-bound lifecycle, not navigation

**Status:** In progress for 1.8

**Date:** 2026-08-26

**Related:** [#991](https://github.com/openonion/connectonion/issues/991),
[#1296](https://github.com/openonion/connectonion/issues/1296),
[#1297](https://github.com/openonion/connectonion/issues/1297),
[#1036](https://github.com/openonion/connectonion/issues/1036),
[#1172](https://github.com/openonion/connectonion/issues/1172),
[DD-053](053-oip-only-browser-and-native-coding-adapters.md),
[DD-054](054-one-async-browser-runtime.md)

## Context

`co call <host> co browser ...` can execute a shell command remotely, but it is
not a Remote Browser protocol. It exposes no durable browser-session identity,
does not bind a session to the authenticated OIP caller, and returns the generic
EXEC result shape. Building a second remote driver would also bypass the tab
claims and one async runtime established by DD-054.

Navigation is a separate security boundary. Checking only the submitted URL is
not sufficient: redirects and subresources can reach loopback, link-local,
private-network, metadata, or otherwise prohibited destinations after the first
request appears safe.

Relay adds another boundary. OIP identity signatures authenticate commands but
do not make the Relay blind to browser-control content. Relay Remote Browser
therefore depends on the reviewed secure channel tracked in #1172.

## Decision

The first 1.8 slice introduces a typed, signed `REMOTE_BROWSER` OIP frame and a
stable `REMOTE_BROWSER_RESULT` envelope. It supports only `start`, `status`,
`sessions`, `stop`, and `diagnose`.

The Host derives the owner from the authenticated OIP connection. A request
cannot supply or replace it. Only contacts, whitelisted callers, and admins may
use the service. Session IDs locate records but grant no authority: another
caller receives the same not-found response as a nonexistent session.

The Host owns one persistent, mode-0600 session registry and delegates tab
lifecycle to the existing Browser daemon. The authenticated owner is also the
daemon tab owner. Start is idempotent by owner and request ID; Stop keeps a
tombstone and is idempotent. Host restart reloads the same registry rather than
minting new authority.

Only a direct OIP transport and `proxy=direct` are admitted in this slice. Relay
fails with `SECURE_CHANNEL_UNAVAILABLE`; other proxy modes fail with
`REMOTE_SESSION_PROXY_LOCKED`. Neither condition silently falls back. Navigation
is absent, and `diagnose` reports `navigation_policy: not_enabled`.

## Consequences

- Remote Browser is not a wrapper around generic shell execution.
- The daemon and async core remain the only browser runtime.
- Lifecycle, identity, retry, reconnect, and Host-restart behavior can be tested
  before URL access is exposed.
- The first useful release is deliberately narrower: it cannot yet navigate,
  capture, act, take over, or release.
- Navigation may land only with a policy enforced across initial requests,
  redirects, DNS changes, and subresources.
- Relay may land only after #1172 supplies the reviewed, downgrade-resistant
  secure channel.

## Revisit

Extend the command set when #1297 has executable negative
tests and the same lifecycle conformance suite passes through the installed
artifact. Enable Relay only after its secure-channel vectors pass in every OIP
implementation and the Relay sees no command plaintext.
