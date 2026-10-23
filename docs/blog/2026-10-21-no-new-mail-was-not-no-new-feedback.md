# No new mail was not no new feedback

Candidate implementation; not included in the published 1.9.3rc16 preview.

A saved correction can arrive after a page's last investigation. We asked what an
explicit investigation would do if the mailbox and coding sessions had nothing new.
Two synthetic tests supplied the same empty window: one with a correction, another
with an answered question. Both stopped before the feedback reached a model. The
message said there was nothing new.

Adding assertions to the mail packet would have defeated that shortcut, but it
would also have mixed different kinds of evidence. A correction is attributed
context. It does not establish another contact or a fresh research window, and it
should not disappear into a digest of old messages.

The fallback therefore does one maintenance turn for the declared page, using the
original feedback records. Its result says `feedback_only`. Accepting that turn
records which input reached the page; it leaves the investigation date alone.
An empty window without pending feedback still spends no model call.

Review uncovered a concurrency problem while following that turn. A model could
read one version, reply “no change”, and have that answer acknowledged against a
page another writer changed in the meantime. We reproduced it by changing the
canonical page inside a fake model call. No-change now checks the original page
under the same promotion lock used for an edit before it can become an acceptance
proof. Leaving a file untouched is still a judgment about a particular snapshot.

This is a limited repair to the empty-window path. It does not prove that an
assertion is true, complete the external-agent workflow, or settle receipt handling
for mixed-source and multi-round investigations. Logs keep the distinction so a
feedback review cannot quietly become evidence that new research happened.


The 23 October integration inherits current main's reviewed Python 3.11 minimum
and dependency lock. It does not waive the old dependency audit failure. The
empty-window fallback, accepted-target receipt and native no-change snapshot check
remain the same contract. Matching source and public CLI documentation must be
reviewed together before this candidate can ship. No real model, mailbox or
scheduled maintenance was run for this integration; synthetic acceptance cannot
establish the factual quality of a corrected memory.
