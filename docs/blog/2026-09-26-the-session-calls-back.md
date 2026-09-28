# The test finished after the Agent said goodbye

Status: draft Design Journal for #1788. Publish after the session watch package is released.

An Agent started a CRCD job that could take half an hour. It gave the user a
useful answer and ended its turn while the process kept running. When the test
finally exited, the machine knew the result. The conversation did not. The
Agent had no next iteration in which to notice it, and the user had to come
back and ask whether the work was finished.

We first tried putting a watcher in the network Host. It could notice a file
change or a timer and start a dedicated watch conversation. But it answered a
different question: the Agent wanted to follow *its own* task and return to
the session where the promise was made. A local Agent runner should be able to
do that without starting a network Host. The 1.8.9b9 Host preview remains a
historical release; its watcher code is being removed from later builds.

The missing handoff sits between a source and a session. A background task
writes its completion receipt. A recurring Gmail check compares message IDs
with the last durable baseline; an unchanged mailbox spends no model call.
Either source can write an observation addressed to the original session. If
that session is in the middle of a turn, the existing `watch_events` plugin
adds the observation before the next model decision. If the turn has ended, a
small session service claims the conversation and starts another turn in Read
only mode. The user sees the observation, then the Agent's conclusion.

A crash made this less simple than an in-memory callback. The process can die
after saving the Agent's answer but before marking the observation delivered.
Retrying blindly would ask the model to work twice. Each observation therefore
has an ID in the session trace. Recovery checks the saved turn before it
requeues anything. An interrupted turn does not count as an answer; a naturally
finished one does. We still cannot promise exactly-once effects outside the
session when a process dies at an uncertain point, so unattended turns begin
with Read only permissions.

The boundary now belongs to the session service, which accepts a callback to
run a session turn. `co ai` supplies that callback and starts the service; a
local runner can do the same without `host()`. A process must still be alive to
check the clock or wake an idle conversation. When it restarts, the persisted
watch and any pending observation give it somewhere honest to resume.
