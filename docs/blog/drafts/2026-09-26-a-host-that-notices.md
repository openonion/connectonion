# A Host that notices (draft)

Status: draft for the 1.8.9 preview. Publish only after the tagged package and
GitHub Release are visible.

The missing piece was the space between events and turns. A lifecycle hook
cannot hear a file change while the agent is idle: there is no turn in which
the hook could run. The Host could already accept a chat message or a scheduled
prompt, but those paths were wired separately.

The watcher now keeps observation cheap and turns ordinary. A file change or
timer firing first becomes a durable event. The Host then feeds that event to
the same input path as a conversation prompt. It reaches the agent as a user
message in a stable session, and the result lands in the existing session log.

We chose a persistent queue because a model may spend minutes answering an
event, while observing another source should take milliseconds. A Host restart
must not erase events it has already seen. The queue also lets the operator see
which watch fired, which session handled it, and what failed.

There is a deliberate limit: a two-second file poll detects the latest file
state, so rapid intermediate writes can combine. A watcher tells the agent
that something happened; it is not a filesystem journal. The same event
envelope can later accept inbox and callback producers without changing the
agent's input path.
