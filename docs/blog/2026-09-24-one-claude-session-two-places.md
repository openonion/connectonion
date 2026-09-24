# The answer appeared before the turn was finished

The terminal had already answered. In a local trial, we opened its Claude Code
session in O Chat, took control from the browser, and sent one short Haiku
prompt: reply with a fixed token. The token appeared in the Work Room. Then we
clicked **Return to terminal**. The Host replied `provider_busy`.

That looked contradictory from the browser. The answer was on screen; the turn
seemed over. The browser had done exactly what we expected a person to do. The
failure sat between two different facts: the transcript reader had seen
Claude's text, but the Host worker had not yet persisted the direct turn's
`done` state. Our return command required that durable state before starting
the terminal again, because otherwise both processes could write the same
Claude session at once.

We followed the two timelines instead of loosening the writer rule. The
Work Room received provider messages as the transcript grew. The Host marked
the worker done only after the native process completed and its result was
stored. Usually those moments are close together. A fast browser click can
land between them, especially when the answer is a single short line. The
first implementation treated that ordinary interval as a permanent refusal.

The return path now waits briefly for the active headless turn to reach its
durable end, then transfers control. If the turn stays active, the browser
still gets `provider_busy`; it does not start a second writer. We repeated the
local journey from a fresh terminal: Claude answered there, the browser paired
and took control, Haiku continued that same session, and the return button
brought back a live terminal with the browser's prompt and answer visible in
its history.

This is why the Station keeps two kinds of state. Transcript text tells a
reader what Claude has said. A revisioned control event and a workspace writer
lock decide who may speak next. The browser can watch a terminal without
owning it, and a signed takeover stops and reaps that terminal writer before a
browser message resumes Claude. Seeing an answer is useful evidence, but it
is not permission to start another writer.

The beta keeps the terminal process alive while its Work Room is available.
The trial covered the handover and same-session continuation; live file-edit
approval is still a separate acceptance step. The narrow race was the useful
finding: a UI can be ahead of durable execution, and control transfer has to
respect the latter while remaining patient with the former.
