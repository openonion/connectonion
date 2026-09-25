# The "n" that start ignored

A re-tester went through the 1.8.8b9 previews with fake `codex` and `claude`
binaries on the PATH. The fakes were shell scripts that wrote down their
arguments and printed a canned answer. No model ever ran. The point was to see
what `co` does around a model, and the part that worried us most was the
consent step.

`co wiki start` is where you agree to let an unattended job read your mail and
coding sessions and send them to a model. It prints a summary first: which
sources, which runner, what that runner is allowed to do, and the schedule.
Then it asks. The tester approved it with the Codex runner and stopped it.
Next they ran `co wiki config set runner claude-code` and started it again,
piping in `n`.

The output was `Started: Yes`, `Consented: Yes`, and the launchd job was back.
No summary was shown, and the `n` was never read.

## A timestamp is not a consent

In the code, consent was one file holding one timestamp. `start` asked only
if that file was missing, or if a newly added source had not been approved yet.
We had already fixed the second case once: a WhatsApp chat added after the
first start could never be read, because nothing asked about it. That fix
treated consent as being about sources. The summary covers more than sources,
though. Moving from Codex to Claude Code means a different company's model and
a different sandbox, and the old approval covered neither.

The fix records a fingerprint of the whole summary, every line of it, when you
say yes. The next `start` compares it with the summary as it would print now.
If anything differs, including sources, runner, model, permission mode,
schedule or limits, the summary is shown again and your answer counts. An
approval saved before the fingerprint existed counts as changed, so it is
asked once more.

Fixing that exposed a second problem. With the runner set to Claude Code, the
summary said your messages would go "through your own Codex login". The line
was a string constant written when Codex was the only runner. It now comes
from the runner. A consent screen that names the wrong provider is worse than
no screen, because people trust it.

## The child that outlived its parent

The same session turned up a process leak. `co claude run` starts `claude -p`
in its own session so that a Ctrl-C in the terminal cannot cut a turn in half.
The tester sent SIGTERM to `co` instead. `co` exited with 143 and removed its
temporary Hook directory. Fifteen seconds later `claude -p` was still running
under launchd, with every Hook it called pointing at a directory that no
longer existed.

We had a SIGTERM handler, added earlier to make sure the Hook's bearer token
did not outlive the run. It deleted the directory and raised `SystemExit`,
counting on the caller's cleanup to kill the child. That cleanup caught
`KeyboardInterrupt` and `Exception`. `SystemExit` is neither, so it went
straight past. Because the child lived in its own session, nothing else would
ever signal it.

Now the handler stops each Claude process that `co` started, signalling its
process group, waiting briefly and then killing it, before it touches the
directory. The read loop also ends the child on any `BaseException`. The test
does what the tester did: it runs the real `co claude run` against a shim that
sleeps, sends SIGTERM, and checks that the shim is gone and that it still
found its settings file when the signal arrived.

## What the rest had in common

Most of what remained was output describing a state other than the real one.
`First batch: Unknown` after a second start, when the truth was "only the
first start runs one". `No page matches` for a file that existed but was a
symlink, when `show` already explained why it was refused. "Run init to build
the map" printed just after init had built it. A TikTok plan that touched no
browser pointing to `co browser tab ls`. Share mode printing a traceback that
ended in `Claude Station terminal failed`, when `--no-share` printed the actual
reason in one line.

None of these crashed, and each one sent someone to the wrong place. The
consent bug belongs in the same group. `Consented: Yes` was a true statement
about a file on disk and a false statement about the person at the keyboard.
Getting the output right mostly means deciding what a line is about and making
sure it stays true.
