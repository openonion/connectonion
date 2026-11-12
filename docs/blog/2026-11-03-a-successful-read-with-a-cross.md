# A successful read with a cross

A mailbox read succeeded, but `co rem status` put a cross beside it. Nine
queued messages had disappeared from the provider. The notebook dropped
those missing entries and kept going, then told its owner to check the logs.
The status line made routine queue cleanup look like a broken mailbox.

The count was useful. Removing it would hide why the queue had shrunk.
The mistake was carrying that count through the same string as a failed
read: any message from that function became a cross and a logs command.

Read health now returns a failure reason and an informational note
separately. A successful read keeps its date and dropped-message count,
with a check and no mailbox logs prompt. Recorded failures still get a
cross. So does a scan more than two days behind when syncs have run.

Before the fix, the regression reproduced the misleading cross for both
Gmail and Outlook using fake mailboxes returning missing-message responses.
It checks the rendered mark, the retained note and the absence of a logs
prompt. The failure and stale-scan checks protect the cases where a cross
still tells the owner something needs attention. A diagnostic can explain
what happened without asking for a repair.
