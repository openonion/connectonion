# The index was not the original

A saved page cited two emails. Both originals were retained on disk. Neither had
a row in the derived message index, so the reader could not show them. A person
trying to check the page had evidence and still could not inspect it.

The index is useful for finding conversations, but it is not the archive. Making
opening a cited original depend on a complete index gave that derived projection
more authority than the retained material. Rebuilding the whole index during an
open would hide a write and complicate read-only inspection. Querying the mailbox
again would add authorization, network and historical-version uncertainty.

The proposed repair reads only deterministically addressed local candidates and
verifies provider, native identity and full archive filename. It requires one
unique identity across native and short-hash interpretations. Independent review
caught a subtle ambiguity: one message's short hash can be another message's
native ID without any cryptographic collision. Choosing either would show an
unrelated original. A real-SHA regression now requires refusal in that case.

Existing indexed identity rejection, privacy, excerpt budgets and capture metadata
remain in force. A source without a known indexed conversation does not acquire
an invented thread. A primary retained snapshot precedes an observed copy of the
same message, following existing archive precedence.

The candidate recovered four previously unavailable originals in a read-only
recheck, while all587 notebook page hashes stayed unchanged. This makes checking
claims possible; it does not establish that those claims are faithful. The wider
semantic sample still has truncated attachment previews and an uninvestigated
project. Native popup/phone acceptance and publication remain pending. No model,
provider, init or scheduler was run and no real notebook page was rewritten.
