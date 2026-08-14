# DD-044: One operator-owned plugin per coding provider

**Status:** Accepted for Alpha.2

**Date:** 2026-08-14

**Related:** [DD-043](043-claude-code-live-tool-events.md), [GitHub issue #986](https://github.com/openonion/connectonion/issues/986)

## Problem

Codex and Claude Code existed as useful tools and COAI wrappers, but installation,
authority, and frontend identity were split across those surfaces. Flattening
child activity also made the parent conversation hard to follow.

## Decision

Each provider has one configurable plugin which installs its public tool. The
plugin binds workspace and permission state before the model sees the schema.
The existing native transports remain replaceable implementation details.

One invocation emits a provider-neutral lifecycle parented to the outer tool
call. Child activity carries the same correlation, remains bounded/redacted,
and is persisted for replay. React owns normalization; O Chat renders one
inline expandable card and retains generic fallback behavior.

## Alternatives

- COAI-only wrappers were rejected because third-party Agents would need to
  duplicate provider policy.
- A provider session browser was rejected as broader than a linear Alpha.2
  delegation.
- Raw terminal embedding was rejected because it leaks provider detail and
  weakens transcript ownership.

## Tradeoffs and limits

Claude Code's current headless stream cannot round-trip every interactive
permission request, so unsupported Manual actions fail closed. A configured
workspace is a launch boundary, not an OS container. Alpha.2 supports ordinary
linear delegation and one or two expanded cards, not a persistent agent graph.

Revisit the transport when Claude exposes a compatible approval-aware API, or
revisit the UI contract when concurrent persistent provider sessions become a
real product requirement.
