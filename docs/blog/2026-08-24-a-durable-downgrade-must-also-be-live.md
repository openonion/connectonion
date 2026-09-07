# A Durable Downgrade Must Also Be Live

The RC3 release gate raised a Codex Work Room to Full Access, then lowered the
outer Host mode to Auto. Storage did the safe thing: it reconciled the provider
profile back to Codex's workspace boundary and recorded a newer lifecycle
revision. The open Work Room still displayed Full Access for more than thirty
seconds.

That was not only stale presentation. A remote coding client is part of the
authority boundary. If it keeps showing broader access after the Host has
withdrawn it, the person cannot tell which policy governs the next instruction.
Reconnect happened to replay the narrower durable state, but reconnect is not
an acceptable security protocol.

The bug lived between two correct pieces. The atomic mode transaction already
appended every provider downgrade it caused. The WebSocket handler acknowledged
only `mode_changed`, so the current connection never received those appended
provider revisions. Persistence and streaming had different ideas of what one
completed transaction meant.

The handler now returns the provider permission revisions created by that exact
atomic update. It sends `mode_changed` first, followed by only those revisions.
The existing storage helper keeps its original return contract for other
callers, and repeating Auto does not manufacture another provider event.

A direct WebSocket regression starts with a committed Codex Full Access
profile, lowers the Host ceiling, and proves that the same connection receives
the newer `codex:workspace-ask` state with Full Access marked unselectable. The
adjacent permission, Work Room, mode, and version suites pass 95 tests; the full
suite passed 7,169 tests with 18 skips apart from a separately corrected docs
checkout version drift.

The release lesson is simple: durable state is the source of truth, but an open
client does not become truthful by waiting for reconnect. When one transaction
narrows authority, its live revision is part of the commit's observable result.
