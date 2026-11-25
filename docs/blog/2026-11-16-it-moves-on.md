# It moves on

*2026-11-16*

This morning's release told the agent what to do when preparing a task takes
more than ten minutes: "Run co rem next again: it moves on to the next work."
On the owner's Mac a scheduled turn did exactly that, three times. Each call
spent its ten minutes on the same person's page. The agent wrote "Nothing was
submitted", and the turn was saved as completed, exit 0.

The sentence was false. One call can pass over several pages before it reaches
the one that hangs, and the round was saved only when a task was served. The
note left by the stalled call named place 98 in the list; the saved round said
97. The next call compared the two for equality, found no match, and began
again at 97. The page is now parked by its name, with the reason in words, and
pages passed over are saved as the call goes.

Stack dumps from that Mac put the ten minutes in one place: reading
coding-session logs, gigabytes of them, to find the few lines the owner typed
about one person. We keep those lines so each log is read once. In the code we
found that we threw them all away whenever a log we had read was no longer a
plain file, and Codex compresses old logs in place. After the first
compression every page read the whole store again, and a read ended by the
deadline kept nothing. A compressed log is now read once more, by itself, and
the work is saved as it goes.

The turn record now says failed, that the turn produced nothing, and which
step it was waiting on. On generated logs the page after a compression read
429.5 MB before the fix and 20.6 MB after. We have not yet run the fix on that
Mac, so we cannot say this was the whole of its ten minutes.
