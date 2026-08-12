# DD-047: Give network ACP one virtual workspace root

**Status:** Accepted

**Date:** 2026-08-12

**Related:** [DD-029 Persistent ACP Session Ownership](029-acp-persistent-session-ownership.md), [DD-033 ACP stdio MCP Authority](033-acp-stdio-mcp-authority.md), [DD-045 Authenticated ACP WebSocket Gateway](045-authenticated-acp-websocket-gateway.md), [Issue #917](https://github.com/openonion/connectonion/issues/917)

## Context

ACP `session/new` and `session/resume` include a `cwd`. For stdio, the client is
a local process launched by the same operator, so selecting an existing
absolute directory is useful and does not cross a network trust boundary.

The network endpoint has a different authority model. Authentication grants a
caller access to the project served by this `co ai` process. If the same `cwd`
rule were reused literally, a remote browser could name any existing absolute
directory on the Host. Read-only mode would reduce mutation authority, but it
would not authorize disclosure of a different project. A browser path also has
no portable meaning on the Host.

## Decision

Network ACP exposes exactly one protocol workspace root: `/`.

When `co ai` starts, it resolves and binds the launch directory object before
the Host accepts connections. On POSIX it keeps an open directory descriptor;
on platforms without descriptor-relative directory entry it records the
directory identity and verifies it before and after entry. A later rename,
symlink, or replacement at the old pathname therefore cannot redirect a turn.
If the platform or filesystem cannot provide a stable nonzero directory
identity, network ACP fails closed at startup.
Every network ACP adapter receives that immutable binding. `session/new` and
`session/resume` map the exact protocol string `/` to it. Every other value
fails as invalid parameters before session ownership, MCP startup, or Agent
construction.

The public protocol never returns the real Host path. Traversal spellings,
symlink aliases, absolute Host paths, and path-like hints in extensible metadata
cannot select a workspace. `additionalDirectories` remains unsupported and
fails closed. Metadata is not an authority source. Network snapshots also store
the virtual root as protocol data rather than resolving it through Host path
semantics, and use the bound directory
identity as part of their private principal namespace.

The shared ACP lifecycle adapter takes an explicit optional bound
`network_workspace`. Stdio leaves it unset and keeps its existing absolute-path
behavior. All adapters share one process-context lock because `cwd` and stdout
redirection are process-global. This makes the transport boundary visible
without duplicating the session implementation.

## Rejected alternatives

- **Accept any existing absolute path after authentication:** admission to one
  launched project is not authority over the Host filesystem.
- **Allow paths beneath the launch directory:** it leaks Host path structure
  and creates platform-specific normalization and symlink rules that the
  browser does not need.
- **Use the browser's local working directory:** it describes a different
  machine and cannot safely name a Host resource.
- **Infer the workspace from ACP metadata:** extensible metadata is untrusted
  application data, not an authority channel.
- **Change stdio to `/` too:** local editor and CLI integrations legitimately
  choose their project directory; no network boundary requires that break.

## Compatibility and rollback

Stdio clients are unchanged. Native network clients in the 1.7 preview must
send `/`; no released browser used the native endpoint before this rule. If the
network endpoint is rolled back under DD-045, the legacy `/ws` route and stdio
ACP path behavior remain unchanged.
