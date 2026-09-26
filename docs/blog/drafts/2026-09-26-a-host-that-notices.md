# The file changed. Why didn't the agent wake up?

Status: draft for the 1.8.9 preview. Publish after the tagged package and
GitHub Release are visible.

Issue #1499 asked for an agent that notices events by itself. Picture a Host
waiting quietly while `notes.md` changes. The tempting answer was to add a
`before_iteration` hook that checks the file. I followed that path through the
code and found the catch: every iteration begins *after* somebody calls
`agent.input()`. While the Host is idle, the hook never runs. There is no turn
to attach the file change to.

The Host already had two ways to start a turn without a person typing in the
UI. Its scheduler starts a turn when the clock fires; its inbox consumer starts
one when a chat message arrives. Both eventually call `input_handler()`. That
was the useful discovery. The missing piece was a common way to record an
observed event before asking the agent to do anything with it.

We first separated the two jobs. A small background poll records a file change
or timer firing in a durable queue. A worker then reads the event and hands its
envelope to `input_handler()` as a user message in a stable session. The agent
can be busy for minutes; observation does not have to wait for its answer.

A restart exposed the harder edge. Suppose the agent's answer reaches the
session log, then the process dies before the queue records completion. Blindly
retrying would give the agent the same event twice and might repeat a tool's
side effect. Recovery now checks the saved session for that event ID before it
starts another turn. It cannot promise exactly-once external side effects after
an uncertain crash, but it can avoid repeating a turn whose completion is
already in the Host's own record.

The lesson was about where to put the boundary. A hook helps an agent *during*
a turn. A watcher must first make a turn possible. The queue makes that handoff
survive a restart and gives the operator a place to see what happened.
