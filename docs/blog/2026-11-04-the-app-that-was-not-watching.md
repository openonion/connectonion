# The app that was not watching

The first dry run of the new `co init`, in a clean home on a Mac, went well
for four minutes. Identity, skills, the mailbox offer, the consent summary,
`y`. Then `Installing REM upkeep.`, ninety seconds of nothing, and a Rich
traceback ending in:

```
RemError: Codex has not registered the paused REM task. Open Codex desktop
and its Scheduled page, let initialization finish, then run `co rem start` again.
```

The message is a good one. It was written for `co rem start`, where it
arrives as one line with a `Next:` because every `co rem` command goes through
the same error renderer. `co init` calls the REM step directly, so the same
error came out as thirty lines of stack. First impression of the product, on
the first command.

The cause was not the clean home. REM's scheduler on a Mac with the Codex app
is a Codex Scheduled task: `co init` writes the task file and waits for the
app to adopt it. The app adopts tasks from one home, the one it was started
with, and it was not watching this one. A user sees exactly the same wait and
the same error when the app is installed but closed at setup time, which on a
new machine is most of the time.

Two changes. The `init` command now catches `RemError` at its boundary and
prints the message and `Next: co rem start`, the way the other commands do;
consent is already recorded by then, so the retry costs nothing. And when the
native registration times out, `co init` falls back to launchd for upkeep and
says so in the summary line:

```
Scheduler installed: launchd (Codex did not register the task; co rem start
switches to Codex Scheduled once the app is open)
```

The notebook gets its nightly clock either way, and the better scheduler is
one command away once the app is running.

The dry run also showed the consent summary as it really looks: every limit,
the WhatsApp folder path, the timestamp of a source nobody subscribed to, and
the question at the bottom of a screenful. That is #2758's second half and a
separate change.
