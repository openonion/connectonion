# An Action Is Not a Reason

We asked an agent whether a machine was ready for release. It called
`inspect_system` with `uname -a`, and the first version of the interface put a
field named `reason` above the call.

That small name changed what the model wrote. Instead of a crisp activity such
as “Check the operating system,” the transcript began explaining itself: “I
need to inspect the operating system because the user asked me to verify release
readiness.” The sentence was longer than the useful result, repeated the user's
request, and presented a generated account of motivation as though it were an
observable fact. On a phone, it also turned one quiet tool event into a block of
prose.

The failure was not in the tool. The function still received the right command
and returned the right kernel version. The failure was in the contract we had
given the model: ask for a reason, and it will try to justify itself.

The useful line was already hiding inside that explanation. “Check the
operating system” says exactly what a person watching the run needs to know. So
the 1.7 contract now calls the field `summary` and describes it as a short action
phrase. The reader places that phrase beside the status and duration, then keeps
the tool name, arguments, and raw result behind an expandable detail row.

Changing the name also forced us to decide what happens outside the happy path.
Old recordings and third-party clients do not have a summary, so they still run
and receive a deterministic label derived from the tool name. Ordinary tools do
not receive presentation metadata as an unexpected argument. A tool that
already declares a real `summary` parameter keeps its own value, while the trace
still records the bounded activity phrase shown to the reader.

When we replayed the same release check, the transcript finally read like an
activity log: “Check the operating system · 1.2s.” The command and its output
were still one click away, but the default view no longer pretended to know the
agent's inner motivation.

That is the distinction worth keeping: report what is happening, reveal the
evidence on demand, and leave “why” to the conversation where it can be examined
rather than asserted.
