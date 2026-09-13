# The notebook stopped before its first model turn

**Design Journal draft. This foundation PR is not a shipped organizer.**

The Wiki started with a small ambition: preserve why a decision was made, then
correct that account when the user changes their mind. The user did not want
another inbox of proposed edits. The AI should maintain Markdown itself.

We wrote a file boundary and an incremental session reader, then a Codex adapter
with four notebook operations. Synthetic tests could write a decision, replace
it, and leave unchanged input alone. At that point the pieces looked connected.

The native handshake changed that impression. Passing an empty MCP map to
Codex 0.147.0 did not erase inherited configuration: two servers remained in the
effective settings. The thread accepted the requested model and read-only
sandbox, but those replies did not prove that only our notebook tools existed.
No model turn was needed to discover the discrepancy.

We added a regression and refused that configuration before inference. This
made the first PR less impressive to demonstrate, but more accurate: it held a
tested file core and an inspection CLI, not an unattended organizer. The refusal
itself ran after process startup, so it was not evidence that inherited
integrations could never initialize. Isolated startup remained follow-up work.

The next surprise came from CI. Python 3.10 through 3.13 could not even import
the notebook. Its method named `list` shadowed the built-in used by the later
`search` return annotation. Python 3.14, used locally, deferred evaluation and
let the focused suite pass. Explicitly resolving that annotation reproduced
the failure locally; postponing annotations fixed it, and the new regression
forces resolution rather than trusting a successful import.

Neither failure was about deciding whether a fact belongs under Principles or
Decisions. They were about the wrapper we needed before testing that judgment.
We kept the semantic work in the Skill, but stopped treating passing synthetic
tests as evidence for native isolation or a working product. The next milestone
has to earn those claims with an actual conversation, correction, and readback.
