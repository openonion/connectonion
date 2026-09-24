# The part that was refused was the part we cut

An unattended `co ai` run stopped at 28 of 300 iterations with nothing done, and
the log said a bash command had been denied. It did not say which. Working it
out meant reading the policy source and replaying candidate commands until one
failed the same way; the answer was a pipe into `head`. That became #1493:
log what was refused.

A contributor sent the fix — when a tool call is refused, finish the pending
call line with a failure mark instead of dropping it. Before merging it I ran
it against a real logger rather than the mock in its test, and at first saw no
change at all. That turned out to be my own mistake: running a script by path
puts the script's directory on `sys.path`, so I had been importing the main
checkout, not the branch. With the right code loaded, the line appeared:

```
[co]   ▸ bash(command="CO_WHO=lidaily c...")           ✗ 0.00s
```

And there was the real bug. The call line is truncated to fit the terminal, so
the one command that needed diagnosing was cut off before `| head -40` — the
exact segment the policy refused. For a call that ran, truncation costs little:
it left effects, and the effects explain it. A refused call left nothing, so
the log line is the only evidence there will ever be. Refusals now get one more
line, untruncated:

```
[co]   refused call, in full: bash(command='CO_WHO=lidaily co browser -t lidaily-1000 get_text | head -40')
```

A tool that fails while running does not get it; it was not refused.

The same afternoon, #1292: most `co ai` runs opened with four to six calls to a
tool named `add`, which does not exist. I could not reproduce it — none of the
recent sessions on this machine has one, and the `add(a, b)` example the issue
suspected is no longer in the prompt `co ai` always loads. But the answer the
model got was the other half of the problem: `Tool 'add' not found`, and
nothing else. A model told only "no" guesses again, and guesses the same thing.
It now hears that the tool does not exist, not to call it again, and the names
of the tools it can call.

Both fixes are about the same thing: when the answer is no, say enough that the
reader — a person reading a log, or a model reading a tool result — does not
have to guess.
