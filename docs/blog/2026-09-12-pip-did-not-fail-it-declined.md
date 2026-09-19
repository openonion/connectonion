# pip did not fail, it declined

An old Intel MacBook is our acceptance machine for x86_64 macOS. Someone
reported the paid browser engine would not run on it, so I went to look. The
first thing `co` said there was:

```
BrowserEngineError: onionwright_missing: Run `co browser install-onion`
```

Good error. Names a command. So I ran the command:

```
Could not install Onionwright: pip could not install Onionwright (exit 1).
```

And that is where the trail went cold — except it hadn't, because sixteen lines
above that, pip had explained itself perfectly:

```
error: externally-managed-environment
× This environment is externally managed
...
You may restore the old behavior of pip by passing the '--break-system-packages'
flag to pip ...
Read more about this behavior here: <https://peps.python.org/pep-0668/>
```

pip had not failed. pip had **declined**, on purpose, for a reason it stated,
and had named the flag that overrides it.

## The last line is the one that gets read

Our line was printed after all of that, and it said `exit 1`.

This matters more than it looks. A human skims upward and finds pip's text. An
agent does not: it reads the last line, or it reads the exception message, and
both said an exit code. From there, `exit 1` on an install points at the
download, the release feed, the credentials — every one of which was fine.

And this is not an exotic setup. PEP 668 is the default for Homebrew Python and
for the Python that ships with most Linux distributions. Anyone who did not
build their own interpreter hits it. So the documented path to the paid engine —
an error naming `install-onion`, and `install-onion` naming an exit code —
dead-ends on the ordinary case.

## Two things changed

**pip's output is captured now, and printed back.** Captured, because an exit
code alone cannot tell a refusal-by-policy from a genuine failure and we have to
look at the text to know which one happened. Printed back, because the upstream
text is the evidence — summarising it away would be trading one lost signal for
another. The wheel is about 70 KB, so there is no progress bar worth watching;
nothing is lost by not streaming.

**A policy refusal says so, and names the interpreter:**

```
Could not install Onionwright: this Python is externally managed, so pip will not write to it.

  This interpreter:  /usr/local/opt/python@3.13/bin/python3.13

Install into it anyway — the right answer when `co` itself lives there, because
Onionwright has to be importable by this same interpreter:
  co browser install-onion --break-system-packages

Or put both in a virtualenv, where nothing needs the flag:
  python3 -m venv ~/.co/venv
  ~/.co/venv/bin/pip install --pre connectonion
```

The interpreter path is there because that is the thing the reader has to make a
decision about, and it is not guessable — `co` may be one of four Pythons on
that machine.

## Why we do not just pass the flag

The obvious shortcut is to retry automatically with `--break-system-packages`.
We don't, and the reason is in the name of the flag.

PEP 668 exists because package managers and pip were both writing to the same
site-packages and breaking each other. The marker file is a person or an OS
saying *I manage this one*. Silently overriding it on someone's behalf, inside a
command they ran for an unrelated reason, is the kind of helpfulness that shows
up three weeks later as a broken `brew` and no memory of what did it.

So the flag is opt-in, spelled exactly like pip's own, and the failure message
is the only place it is advertised. The user overrides their own guard, knowingly,
or they move to a virtualenv.

One detail that is easy to miss: the flag is **not** re-offered when it was
already used. If pip refuses with the override already on, suggesting the
override is a loop — the same shape as an error that tells you to run the
command it is refusing.

## Verified where it was found

The test suite proves the classification, but the check that mattered was on the
machine that produced the original message: run it, read the new refusal, then
run the command the refusal prints.

```
co browser install-onion --break-system-packages
→ Installed Onionwright 0.0.14 from the signed OpenOnion release.
```

Printing a command is a promise that it works. The only way to keep that promise
is to run it.

## Postscript: the engine still would not start

With Onionwright installed, the paid engine on that machine says:

```
BrowserEngineError: artifact_unavailable: Use system Chrome on this platform or revision.
```

Which is correct, and a different problem entirely: there is no `darwin-x86_64`
object in the production release bucket. It was built and staged on 2026-09-04
and never promoted, because the native gate failed that day — the same way the
arm64 gate failed that day. arm64 was re-run on the 5th and passed. Intel was
never re-run.

Two unrelated faults, stacked, both presenting as "the paid browser doesn't work
here". Only one of them was ours to fix in code.
