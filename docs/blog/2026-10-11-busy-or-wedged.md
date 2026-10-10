---
description: co browser status now says what is running right now, so a caller can tell a busy daemon from a wedged one without guessing from "Last command".
tags: [Browser, CLI]
---

# Busy or wedged

The browser daemon runs one page command at a time. That is on purpose. It
also means that a scheduled LinkedIn round, stuck behind a slow `scroll`, has
exactly one question to ask before it does anything drastic: is the daemon
working, or is it dead?

Our own skill files tell the agent how to answer it. A timed-out command means
the daemon is busy, they say. Do not `pkill` it. Run `co browser status`.

## The answer that wasn't one

For a while that advice could not be followed at all, because `status` queued
behind the very command you were asking about. One morning a scheduled run
burned eight minutes on four calls, 120 seconds each, and never learned why.
That part got fixed first: `status` is now one of the commands the daemon
always answers, even with every slot taken.

Being answered turned out not to be enough. Here is what a caller saw:

```
Last command: "scroll 3" · 2m ago
```

Two minutes ago, a scroll started. Is it still going? A healthy scroll on that
tab takes 10 to 20 seconds, so two minutes looks bad. But "last command" also
means "the last one that started", and if it finished at second 15, the daemon
has been idle ever since and something else is wrong. The line is true either
way. That is what made it useless: the caller choosing between waiting and
restarting got a sentence that fits both.

## Saying the present tense

The daemon already knew. Every page command registers itself on its tab, with
the line it is running and when it started, so the tab can turn away a second
agent. That record exists only while the command runs. Status now reads it:

```
Busy: "scroll 3" on tab lidaily-0700, running 47s
Last command: "scroll 3" · 47s ago
```

and when nothing is registered:

```
Idle. Last command: "scroll 3" · 2m ago
```

If two tabs are working at once, they share the one `Busy:` line, separated by
semicolons, so a script that greps for `Busy:` gets one hit, not a count it has
to interpret.

Now "running 47s" against a normal 15 means wait, "running 9m" means
something is stuck in that command, and "Idle" with a timeout means the problem
is not the daemon's lane at all.
