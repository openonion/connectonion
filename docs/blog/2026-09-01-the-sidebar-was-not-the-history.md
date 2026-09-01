# The sidebar was not the history

Open the same Chatbot on a laptop and a phone and Recent Chat told two
different stories. Both conversations had reached the same Agent, and both
were retained on the Agent machine, but each browser listed only the sessions
it had created locally. The sidebar looked like history while actually being a
browser cache.

The tempting fix was a timer that downloaded the Agent's JSONL file and merged
it into localStorage. That would have coupled a public protocol to a storage
implementation, leaked the existence of sessions unless every filtering path
was perfect, and made concurrent renames or archives last-write-wins by
accident. Polling was not the missing abstraction. An authenticated session
index was.

Session Sync makes the Agent Host authoritative for retained sessions while
leaving the browser fast. A signed identity discovers only its own summaries,
keeps an opaque incremental cursor, and asks for a revision-consistent
transcript only when needed. Local transcripts still paint immediately and
local drafts survive until the Host has committed them. Remote revisions win
when the two caches meet.

Two details mattered more than the list endpoint. First, looking at Recent Chat
must not create another chat. The SDK therefore opens an authenticated
index-only socket that skips session creation entirely. Second, an opaque
cursor cannot merely be Base64 with a persuasive name. The Host binds and
integrity-protects every cursor by owner, query, and storage generation;
compaction expires it explicitly instead of letting an old position point into
a rewritten log.

The regression boundary ended up spanning storage, protocol, and identity: 14
new Session Sync tests cover owner isolation, monotonic revisions, pagination,
expiry, compaction, archive conflicts, signed legacy-socket compatibility, and
cursor tampering. Another 74 adjacent Host tests cover command signatures,
reattachment, compaction races, modes, and Work Room behavior.

Recent Chat can now become truthful without pretending the network is always
available. The Host is the authority, the SDK transcript is a local cache, and
the sidebar is an index cache. Once those names matched their responsibilities,
cross-device synchronization stopped being a special case and became ordinary
reconciliation.
