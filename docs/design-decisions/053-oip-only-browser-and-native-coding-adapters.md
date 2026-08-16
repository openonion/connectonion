# DD-053: One browser protocol, native coding adapters

**Status:** Accepted

**Date:** 2026-08-15

**Related:** [Issue #1045](https://github.com/openonion/connectonion/issues/1045),
[Issue #1052](https://github.com/openonion/connectonion/issues/1052)

## Context

The 1.7 alpha briefly carried two browser transports plus a generic coding-agent
edge. That split duplicated discovery, session, approval, permission, and event
mapping. It also allowed O Chat to select a base runtime instead of the installed
Codex provider plugin and produced cacheability and missing-executable failures
at boundaries users could not diagnose.

## Decision

ConnectOnion has one first-party browser protocol: OIP 0.1 over the authenticated
Host `/ws` connection. `@connectonion/react` owns the browser client and O Chat
consumes that package without constructing protocol frames.

Codex and Claude Code are native backend adapters. Each launches the provider's
installed CLI using its native lifecycle, keeps workspace and approval policy
operator-owned, and publishes normalized provider, tool, approval, plan, and
result events through OIP. There is no generic third coding-agent adapter.

Provider intent is also an execution boundary, not prompt style. Explicit
Codex run/use/start/open intent routes to `codex()`. A deterministic interceptor
rejects executable Codex commands hidden in shell chains and background/package
wrappers before approval or process creation, while leaving searches and prose
mentions alone. Opening without a task starts the provider thread but no model
turn, so the Work Room can be real without fabricating work.

The removed protocol SDK, gateway, transport discovery, CLI flags, generic tool,
tests, fixtures, exports, dependencies, and product documentation do not remain
as compatibility paths. Rolling compatibility lives inside OIP itself: readers
land before writers, additive fields are ignored by older readers, and an
incompatible authority-bearing value fails once without reconnecting.

OIP 0.1 accepts a descriptor-less CONNECT/CONNECTED peer throughout the 1.7.x
line. That is a bounded legacy reader, not another transport. It may be removed
no earlier than 1.8.0a1, 2026-09-15, and two published preview releases after
privacy-safe compatibility telemetry stops observing it, whichever is later.

Every future rename follows the same clock. Release R adds a dual reader;
release R+1 may emit the new field only after the R reader is publicly pinned in
O Chat; removal is no earlier than R+2 and 30 days after R. Authority-bearing
fields such as identity, permission profile, approval outcome, cancellation,
session ownership, and protocol version are never guessed or coerced. A change
that cannot obey this window requires a new advertised OIP version.

## Consequences

- one socket owns onboarding, reconnect, session state, approvals, permissions,
  interruption, plans, and provider cards;
- transport selection cannot bypass the installed Codex or Claude Code plugin;
- packaged artifacts are smaller and no longer ship an unused protocol SDK;
- preview releases require a published Python package, exact React prerelease,
  exact O Chat pin, and real browser acceptance as one release unit;
- either side can roll back within the documented OIP window without losing the
  session or duplicating prompts/provider cards;
- adding another provider means adding a native adapter and OIP event mapping,
  not another browser transport.
- the generic shell remains useful, but it cannot silently downgrade an
  explicit provider delegation into one opaque command/result.

## Evidence required for release

1. Python unit, integration, CLI, and wheel-install tests.
2. React typecheck, unit tests, clean build, and packed-artifact audit.
3. O Chat browser onboarding with one verification form.
4. A normal prompt and a real Codex delegation with Host logs and screenshots.
5. Equivalent Claude Code acceptance whenever that adapter changes.
6. Routing evaluations, raw-launch false-positive tests, and an open-without-turn
   app-server test whenever provider routing changes.
7. Exact old/new Host and React artifact pairs over Direct and Relay, including
   one-sided rollback, unsupported-version, stale-discovery, approval/provider
   disconnect, duplicate/out-of-order, desktop, and mobile cases.
