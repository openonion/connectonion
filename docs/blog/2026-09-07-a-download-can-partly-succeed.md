# A Download Can Partly Succeed

Draft for 1.8.4; publish after release acceptance.

While adding incoming Gmail attachments, I reached a result that the usual success
message could not describe. The first attachment was on disk. The second could not
be decoded. The command had done useful work and had failed, both at once.

This happened in a deliberately broken development fixture, not a customer's
mailbox. That distinction matters. We had no permission to use a real mailbox as a
destructive experiment. But the operator's next decision was real enough: should
they run the command again? An answer that concealed the first file could lead them
to create another copy. An answer that celebrated the download could make them
stop looking for the missing second file.

Before that complication, even choosing a destination had seemed straightforward.
The selected directory already contained `report.txt`. The message supplied two
more attachments with the same name, one disguised as `../../report.txt`. Opening
the destination directly would replace an existing document. Removing the path
components would stop the escape and leave us with the original collision.

The tempting repair was to check whether a name existed and pick a suffix. That
made the example look safe, but another process could claim the name between the
check and the write. The protection had to hold when the bytes became visible,
not just when we chose what to call them.

So each attachment gets a private temporary file first. Only after decoding,
checking its size and flushing the bytes do we publish it under an unused name.
Placement itself refuses a collision; a competing file makes us try the next
suffix. Existing documents stay where they are. A filename supplied by a message
does not get to choose a directory outside the one the operator selected.

Then the second attachment failed, and a different temptation appeared: remove
the first file so the whole command could be called a failure. That would simplify
the status at the cost of throwing away a completed download. It would also make
the filesystem tell a less useful story merely to preserve a tidy return value.

We kept the file. The result lists its destination and hash alongside the second
attachment's error, and the command exits with status 1. The operator can see which
part needs attention. The failed attachment never acquires a final filename.

The regression now checks the directory as well as the result: the old document
survives, successful bytes have their own names, and no partial second file looks
complete. Those checks establish the local behavior. An authorized disposable
mailbox journey is still owed before release acceptance.

The useful change was in what we meant by completion. We were saving a set of
attachments, not receiving one HTTP response. Once part of that set had reached
disk, a single success sentence—or a single unexplained error—could no longer
tell the operator what had happened.
