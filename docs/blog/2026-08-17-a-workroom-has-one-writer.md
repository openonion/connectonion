# A Work Room Has One Writer

The first long Codex acceptance run did not crash. It did something more
embarrassing: after several real actions, the parent conversation reduced the
agent to a small card that mostly said “Work Room.” The work was there — inspect
the project, write the C sorter, compile it, run tests, pause for a decision —
but a person looking at the chat could not tell what was happening.

That was the reason to use a long run instead of a one-message demo. A short
answer never made the handoff between the provider, the React reader, and O
Chat compete. An eight-step run did. The provider could first report useful
activity, then supply a real workspace image, then pause for approval, and
finally complete. Each update was small and valid on its own. Together they
asked a question we had not made explicit: when the later approval contains no
image, did the image disappear, or is the approval simply newer state that must
keep the last real evidence?

At first that looked like a rendering choice. Put a little merge logic in the
card, preserve whatever field happens to be present, and move on. But the
browser cannot know whether a missing artifact means “keep the old one,”
“remove it,” or “this event belongs to a different invocation.” The same guess
would be even more dangerous for a Stop acknowledgement or an approval. A
beautiful card that lets an old decision settle a new run is not a harmless UI
bug.

The turn was to stop asking the readers to reconstruct a provider session from
a transcript. Core is now the single writer of the bounded Work Room state. It
chooses safe activity words, refuses native commands and paths in the browser
envelope, retains a genuine latest image only when the provider supplied one,
and assigns a revision to every meaningful transition. A later approval or
terminal event can therefore carry the latest valid evidence without pretending
that it produced new evidence.

The React package has a narrower job: validate the envelope, normalize it, and
reject malformed or stale authority. It does not infer a successful command,
invent a thumbnail, or promote a missing revision into an approval. O Chat is
narrower still. It renders the compact snapshot and focused Work Room, then
sends Stop or approval decisions back with the identifiers Core supplied.

The result is quieter than the first version. A running card leads with task,
current meaningful work, and status. A real provider image is bounded so it
cannot push progress below the fold. Detailed activity is folded into the Work
Room rather than copied into the parent conversation. When there is no real
image, the card says what it knows instead of faking a screenshot.

We made the route between the three repositories visible in the boundary
headers: Core writes the contract, React normalizes it, and O Chat renders it.
The evidence follows the same route. Core tests exercise revision and artifact
retention; React tests exercise normalization; O Chat's production-browser
acceptance runs the multi-step coding journey, approval, scoped Stop, and a
phone-width layout.

The lesson was not “add more state to the card.” It was that a live Work Room
needs one authoritative writer and defensive readers. That is the smallest
boundary that makes a long-running coding agent legible without turning the
browser into a second agent runtime.
