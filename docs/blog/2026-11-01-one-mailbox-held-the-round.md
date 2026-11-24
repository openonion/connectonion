# One mailbox held the round

Three mornings in a row, a notebook stopped after roughly thirteen seconds.
Gmail had failed, and the other sources never got their turn. Status still
put a check beside Gmail: “read by the daily round.” That line described its
subscription, not what the round had managed to read.

The collector rotated through sources, but returned on its first error.
The rotation marker stayed behind the failed mailbox. The next scheduled
sync therefore started at the same place and stopped for the same reason.
A temporary provider failure had become a queue that could not move.

We kept the boundary between sources: each batch still takes material from
one source, so its reader gets the right source instructions. A collection
failure now records its reason and lets the next source try. Its own cursor
stays untouched. If another source can be read, the sync completes with a
warning; if none can be read, it fails. The rotation advances even when the
failed mailbox has nothing it can safely checkpoint.

The missing diagnostic mattered too. “HttpError” alone gave no clue whether
to reconnect an account or wait for a provider. The regression uses a fake
mailbox raising a real Google `HttpError 503 Backend Error`. The run retains
that status and a recognized diagnostic phrase, without copying a request
URL or arbitrary response body. Other exceptions keep only their class;
free-form exception text is never stored. Status reduces old run records to
the same safe diagnosis before showing them. The same test checks that another
source's item reaches the reader.

Status now remembers the last collection attempt separately from the cursor.
A failed read gets a cross, its date, its reason and a command to inspect the logs.
A scan more than two days behind while syncs ran says “not read since”
rather than claiming a failure that was never recorded. A successful retry
clears the saved failure, including when the mailbox has
no new items. Being connected is useful; showing what actually happened is
what makes the next morning's status worth trusting.

Archive resume follows the round's outcome: a failed source no longer stops
a completed round from resuming the initial mail archive. A wholly failed
round still skips that work.

Outlook reads now request immutable message IDs, so moving mail between
folders in the same mailbox does not invalidate queued references. Existing
queue entries keep their old IDs; those can still go missing once after an
upgrade. Moving to a separate archive mailbox can also change the ID. When
a queued message returns 404, the round counts it under `dropped_missing`
by source and shows the count in its warning, sync summary and mailbox status.
