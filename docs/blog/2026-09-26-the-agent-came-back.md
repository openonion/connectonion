# The agent came back

An agent can start a command that takes half an hour. Until now, the useful
part of the conversation ended there. The command might finish, but the agent
had no reason to return unless a person asked again. Polling `task_output()`
kept the model busy with waiting rather than the work it was meant to do.

A watch gives that waiting a home in the Host. The agent starts a managed task,
records a watch for its task ID, and finishes its turn. The task runner writes
its final status and a bounded slice of output. The Host stores an observation,
claims the original session, and starts a new turn. The observation is labelled
as source data; the agent's answer is a separate message. A failed command
does not become a successful user task merely because the watcher fired.

The same path handles a recurring mail check. For a request such as “check for
CRCD mail every 30 minutes,” the Host remembers the first set of matching
message IDs. Later checks that find the same IDs use no model turn. A new ID
produces an observation and wakes the original session. The watch has a bounded
life and can be cancelled; a source error pauses it instead of silently
claiming that nothing happened.

The hard part was the boundary between waiting and conversation. A completion
can arrive while a user turn is still running, or just before the agent has
registered its watch. The task receipt is durable, so registration can notice
an already finished task. The Host's existing atomic session claim keeps two
turns from writing the same history at once. On restart, an unresolved task is
reported as unknown rather than guessed to have succeeded.

This first version is for a long-lived `co ai` Host and its owner. It keeps
`co listen` as the separate path for external messages. The offline tests cover
the task registration race, unchanged and changed mail results, restart,
busy-session delivery, and a real short background process. An authenticated
mailbox check remains an installed acceptance step before the 1.9.0 release.
