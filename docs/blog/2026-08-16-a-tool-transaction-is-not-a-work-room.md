# A Tool Transaction Is Not a Work Room

The first long Codex run looked broken in a very specific way. The outer agent
had called `codex`, so the transcript showed a small generic tool row. Inside
that call Codex was reading files, running Python, changing a test, and asking
for permission to run the final check. None of that appeared until the outer
tool returned.

The delay was not a frontend rendering bug. Hosted tools execute through an
interruptible lease. The lease deliberately withholds copied session state and
canonical trace records until the tool has committed, which stops an abandoned
or cancelled tool from writing a late result into the conversation. That is the
right transaction boundary for durable history. It is the wrong boundary for a
human waiting to decide whether a live coding agent may continue.

The fix gives native Codex and Claude Code provider events a narrow live lane.
The provider start, child activity, and terminal state are sent to the connected
reader as they happen, while the identical stable events remain deferred for the
canonical trace. If the reader stops the outer run, the lease sends one transient
`cancelled` provider update and discards the deferred state. It does not turn a
partially executed tool into committed history.

An approval needs the same distinction. The permission request is still owned
and authorized by the Host. Its presentation carries only a provider name, the
provider invocation ID, the parent tool-call ID, and, when available, a child
activity ID. The React client uses those identifiers to place the decision on
the exact Codex or Claude Code card rather than on a same-named generic outer
tool. Absolute operator paths are not reused as UI labels; a provider that omits
its working directory gets a short workspace label instead.

This changed the Work Room acceptance test from “a card eventually appears” to
an eight-step run: inspect files, run a Python algorithm, edit, test, and pause
for approval. During the run there must be one provider card, a current activity
summary, a bounded independently scrollable history, a visible Stop action, and
the approval on that card and in the Work Room. Raw commands and outputs remain
behind disclosure. A visual surface is an honest activity snapshot until a
native provider actually emits a real image artifact; it is not a fabricated
screenshot.

The focused core suite covers the two layers separately: a live provider start
is observable before commit, cancellation closes the live card without leaking
a persisted trace, and a hosted coding tool really streams before its backend
returns. The browser suite then verifies the provider card, the correlated
approval, the bounded eight-entry timeline, and phone-width layout.

The reusable rule is simple: transactional history protects ownership; live
status protects the reader. A Work Room needs both, and neither should pretend
to be the other.
