# The First Correct Snapshot Was Still Wrong

The RC4 gate stopped a real Codex follow-up, then lowered the outer session from
Full Access to Auto. The provider stopped correctly. The outer mode changed
correctly. Storage even contained an Auto-bounded provider snapshot. Yet the
reopened Work Room could retain Full Access.

The failure required a terminal continuation. Stop produced a valid cancelled
provider frame without a permission catalog. While committing the later mode
change, the Host first normalized that frame under the old Full Access ceiling,
which appended a repair snapshot. It then applied Auto and appended the real
downgrade. Both snapshots belonged to one transaction and both were streamed.
The first was individually correct and transactionally wrong.

This is why an authority transaction cannot be reviewed as a bag of valid
events. Its observable result must contain only the final policy. A client that
sees an intermediate broader state may persist or render it before the narrower
revision arrives, especially across reconnect and coalescing boundaries.

The fix makes mode application normalize ordinary session policy without
publishing provider authority. After the requested mode is committed, provider
permissions reconcile exactly once. A stopped continuation therefore produces
one live revision: Auto selects Codex Ask for approval and disables Full Access;
Read only selects Codex Read Only and disables every broader option.

The regression recreates the exact sequence with a terminal continuation that
has no catalog. It proves the WebSocket sends `mode_changed` followed by one,
and only one, provider snapshot at the final ceiling. The release gate will now
repeat the same sequence against native Codex and Claude Code before another
candidate can be promoted.
