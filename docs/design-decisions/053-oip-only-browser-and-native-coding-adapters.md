# DD-053: One browser protocol, native coding adapters

**Status:** Accepted

**Date:** 2026-08-15

**Related:** [Issue #1045](https://github.com/openonion/connectonion/issues/1045)

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

The removed protocol SDK, gateway, transport discovery, CLI flags, generic tool,
tests, fixtures, exports, dependencies, and product documentation do not remain
as compatibility paths. An older client or Host must upgrade as a matched preview
pair.

## Consequences

- one socket owns onboarding, reconnect, session state, approvals, permissions,
  interruption, plans, and provider cards;
- transport selection cannot bypass the installed Codex or Claude Code plugin;
- packaged artifacts are smaller and no longer ship an unused protocol SDK;
- preview releases require a published Python package, exact React prerelease,
  exact O Chat pin, and real browser acceptance as one release unit;
- adding another provider means adding a native adapter and OIP event mapping,
  not another browser transport.

## Evidence required for release

1. Python unit, integration, CLI, and wheel-install tests.
2. React typecheck, unit tests, clean build, and packed-artifact audit.
3. O Chat browser onboarding with one verification form.
4. A normal prompt and a real Codex delegation with Host logs and screenshots.
5. Equivalent Claude Code acceptance whenever that adapter changes.
