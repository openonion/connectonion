# A Name Is Not an Adapter

The user wrote “open the Codex.” The agent answered that it understood, ran
`pwd`, ran `which codex`, and then announced that Codex was ready.

Codex had never started.

The screenshot made the failure unusually clear. Every individual sentence
sounded plausible. The working directory existed. The executable existed. The
base model knew what Codex was. But none of those facts created a provider
session, so there was no Codex activity, no approval boundary, no session ID,
and no Work Room to reopen. A product cannot call that delegation merely
because the model used the delegate's name in its reply.

We first tried the tempting fix: make the prompt more emphatic. Prompts are
useful for policy, but they are not routing tables. A model can still inspect
the shell, explain what it intends to do, or select a generic tool. That is
exactly how the original failure remained fluent while doing the wrong thing.

Alpha 7 moves the invariant to the boundary. Explicit `run`, `use`, `start`,
`open`, `/codex`, delegation, and equivalent Chinese requests are recognized
before ordinary tool selection and given one native route. If a shell tool
later tries to launch `codex`, the call is rejected before approval or process
creation and the rejection is published as an OIP event. Harmless commands
such as `which codex`, documentation searches, and commit messages remain
ordinary shell work; mentioning a provider is not the same as launching it.

“Open” exposed a second assumption. Our tool required a prompt, so even a
correctly routed open request encouraged the model to invent a task. The native
adapter now starts or resumes the Codex thread without submitting a turn when
the user supplied no work. The returned session ID is still the handle for the
next real task. Opening a work room and asking someone to work are different
actions, even when the same API supports both.

The first public browser run exposed one more lifecycle detail: Codex does not
write a resumable rollout until a thread receives its first turn. Alpha 7 could
therefore display a real open-only thread ID and still fail when the Work Room
tried to resume it in a new app-server process. Alpha 8 keeps that initial
app-server alive behind a bounded, fifteen-minute registry. The first follow-up
claims the exact thread, persists it by completing a real turn, and closes the
process. Expiry and a hard registry limit prevent abandoned rooms from becoming
an unbounded process leak.

The useful measurement was not one happy mocked call. The focused suite now
covers 101 routing, adapter, plugin, and co-ai cases, including false positives
and wrapped shell launches. Four authenticated Codex app-server tests exercise
open-without-turn, its same-thread first follow-up, a real turn, and session
resume. The installed wheel is then
tested in a fresh environment so a source checkout cannot accidentally supply
the new plugin. The final browser acceptance remains the most human test: the
same words from the original screenshot must produce a Codex card and an
openable Work Room, not two Bash rows and a confident sentence.

The broader lesson is small enough to reuse: provider identity belongs in the
protocol path, not in prose. If a request must cross a particular authority,
session, or approval boundary, the system should be able to prove which
adapter handled it. The model can decide what to say after that. It should not
get to decide whether the boundary existed.
