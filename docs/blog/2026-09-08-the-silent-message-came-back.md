# The silent message came back

The consumer had nothing to say. That was a valid result: it had inspected the
message, exited successfully, and produced no reply. The mailbox removed the
queue file. Then the same synthetic provider event arrived again, and the message
was waiting for another consumer.

The recovery code was doing exactly what we had asked. An ID in the inbox log
without a queue file or a successful reply looked like a crash between logging
and queueing. Recreating the queue file recovered that crash. It also undid an
intentional decision to remain silent. Once the file was gone, those two outcomes
looked identical.

We could have recorded an empty successful reply. That would have made the
existing duplicate check pass, but the outbox would then claim the provider had
sent something it had never received. Instead, completion now has its own small
append-only record. It is flushed before the queue file is removed. A replay sees
the completed ID and stops; the outbox still says nothing was sent.

The next test changed the replay's chat and body after removing the first queue
file. Recovery recreated those new values while the inbox log retained the old
ones. We now recover from the original logged message. A second delivery is a
reason to recover the recorded operation, not permission to replace its content.

Another fixture left half a JSON line at the end of the inbox. The next append
joined that broken line and disappeared from lookup even though its queue file
existed. Separating a torn tail before appending preserved the new record. Five
regression cases failed on the imported branch, including two unrelated message
IDs that collapsed to the same sanitized filename and a listener lock removed
while contenders could still hold its inode.

There was a race beside these crash cases. Rename preserves a file's old timestamp;
the stale sweep could return a freshly claimed message before the consumer reset
that timestamp. Built-in queue mutations now share a short kernel lock. A test
pauses the claim in that interval and starts the sweep from a second mailbox. The
sweep waits, then leaves the fresh claim alone.

These fixtures make the local boundary more precise. They do not tell us how long
a provider retains events while disconnected. That still needs the real-channel
run before 1.8.5 can claim its listener has passed release acceptance.
