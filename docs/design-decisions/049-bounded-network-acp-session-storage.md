# DD-049: Bound durable network ACP session storage

**Status:** Accepted

**Date:** 2026-08-13

**Related:** [DD-029 Persistent ACP Session Ownership](029-acp-persistent-session-ownership.md), [DD-045 Authenticated ACP WebSocket Gateway](045-authenticated-acp-websocket-gateway.md), [DD-047 Network ACP Virtual Workspace](047-network-acp-virtual-workspace.md), [DD-048 Native ACP Browser Attachments](048-native-acp-browser-attachments.md), [Issue #921](https://github.com/openonion/connectonion/issues/921)

## Context

An authenticated network principal can create many resumable ACP sessions. A
successful prompt replaces its session snapshot with the complete private Agent
continuation state. Inline image data remains inside that state. DD-048 bounds
retained files, but its quota does not count snapshot files or inline message
data. Small successful requests could therefore consume Host disk without
reaching the attachment quota.

ACP `session/close` only releases the runtime-long lease. DD-029 deliberately
keeps the snapshot resumable, so close cannot be reinterpreted as deletion or
automatic eviction.

## Decision

Each authenticated-principal namespace has three independent network limits:

- 100 durable session snapshots;
- 100 MiB of cumulative serialized snapshot bytes;
- 32 MiB for one serialized snapshot.

Operators may lower these with `max_acp_sessions`,
`max_acp_session_storage`, and `max_acp_snapshot_size`. The single-snapshot
limit cannot exceed the cumulative limit. Local stdio ACP keeps the existing
operator-owned storage behavior and is not charged to a remote principal.

The complete JSON candidate is encoded to UTF-8 and measured before commit.
One OS-backed lock serializes accounting across every connection and process in
the principal namespace. While holding it, the writer scans canonical snapshot
files as the only source of truth, counts the union of snapshot and lease IDs,
subtracts the current target bytes on replacement,
enforces all three limits, writes a private temporary file, calls `fsync`, and
atomically replaces the target. Quota failure never changes the previous file;
the ACP prompt transaction restores its last-good in-memory checkpoint.

New-session admission creates its provisional lease ID while holding the same
principal lock. Concurrent admissions therefore reserve remaining slots in a
stable order: one excess request cannot make every otherwise-valid request fail.

Bounded resume scans and opens only canonical regular snapshot files without
following symbolic links. It rejects a store already beyond its configured
limits before decoding JSON and caps the read to the single-snapshot limit.
Unknown entries and scan, stat, lock, or pathname races fail closed. Network
errors remain generic and contain no private content or Host path.

A caller-supplied unknown resume UUID is checked before a lease file is
created. A server-minted new session whose initial snapshot fails is removed
with its uncommitted lease. If request cancellation occurs after initial commit
but before the ID can be returned, that unpublished snapshot and lease are also
removed. A normal returned session, including one later closed, is retained.

## Retention

The 1.7 preview has no silent expiry, LRU eviction, history truncation, or file
reference guessing. Exhaustion fails closed. Removing the whole private
principal namespace while the Host is stopped remains the explicit destructive
operator boundary. A future authenticated delete/expiry method must separately
define attachment references and race-safe reclamation.

## Rejected alternatives

- **A mutable usage manifest:** introduces a second crash-recovery truth that
  can drift from the atomically committed files. A locked scan of at most 100
  snapshots is simpler.
- **Delete on `session/close`:** breaks the accepted resume lifecycle.
- **Truncate old messages or inline images:** makes private continuation state
  inconsistent and silently changes model behavior.
- **Use session IDs as quota authority:** they are routing values; the
  authenticated principal namespace is the authority boundary.
- **Count only retained files:** inline images and all other serialized session
  state would remain unbounded.
