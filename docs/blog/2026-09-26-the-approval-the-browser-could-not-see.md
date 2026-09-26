---
tags: [Permissions, Work Rooms, Claude Code]
---

# The approval the browser could not see

Claude was waiting for permission to write a file. The browser had received
the approval request, but its Work Room still said “Working.” There was no
button to press. Waiting longer did not help because both sides were obeying
their own state: Claude's Hook blocked for an answer, while the browser showed
approval cards only when the provider lifecycle said it was awaiting approval.

The missing event sat between those two facts. The native PermissionRequest
Hook forwarded an OIP `approval_needed` message, but the provider invocation
remained `running`. We reproduced the stall with a real Haiku turn after a
terminal-to-browser handover. The WebSocket frame arrived and the file was
never written.

The fix emits a revisioned `awaiting_approval` lifecycle event before asking
the owner and a `running` event after the decision. The same browser test then
showed **Allow once**; accepting it let Claude write the exact requested file
and reply. Focused unit tests cover event order and revision increase.

The test also exposed a misleading permission menu. Station always uses
Claude's native default mode for browser turns so the owner can review edits,
yet the Work Room offered “Auto.” Station now declines profile changes and
stops advertising the profile catalog. The UI displays its fixed approval
policy instead.

This closes one visible gap, not the whole distance to Happy. Our bridge still
asks the owner only about workspace file edits. Shell commands, MCP calls,
questions, and plan changes need explicit presentation and decision rules
before the Work Room can offer the same control without weakening its
workspace boundary.

The bridge fix is included in the opt-in 1.8.9b4 preview. The O Chat label
change is tracked separately, so installing the Python preview alone does not
change the already deployed browser interface.
