# The exit code at the bottom

An agent runs a test suite. The output is long — a few thousand lines of dots,
skips, warnings — and the tool caps what it returns at 10,000 characters. What
comes back ends like this:

```
... (truncated, 12,014 total chars)
```

The agent reads that, says "tests ran, output truncated", and moves on. The suite
had failed. Nothing in the returned string said so.

Nothing lied, either. The tool builds its answer in three pieces — stdout, then
stderr, then `Exit code: N` — and truncates the joined string from the right. The
one line that distinguishes success from failure is the line at the very bottom,
so it is the first thing the cap removes.

## The framing is not output

The command produced stdout and stderr. The exit code, the `STDERR:` label and
the truncation note are the tool's own words about the command. Treating them as
part of the same blob meant the cap could delete the tool's conclusion while
keeping 10,000 characters of the command's noise.

So the cap now applies to the streams, and the framing is reserved first:

```python
remaining = MAX_OUTPUT_CHARS - (len(status) + 1 if status else 0)
if stderr:
    stderr = _fit(stderr, remaining - 1, "stderr")
    remaining -= len(stderr) + 1
if stdout:
    stdout = _fit(stdout, remaining, "stdout")
```

Stderr gets the space before stdout, because when a command fails, stderr is the
part that explains why. A command that fails loudly and prints nothing to stdout
now arrives as `STDERR: ...` followed by `Exit code: 1`, even if it wrote a
megabyte to stderr.

Each stream keeps its own note, so a cut is still visible and still says how much
was cut:

```
xxxxx...
... (stdout truncated, 12,000 total chars)
Exit code: 3
```

## What was measured

A command printing 12,000 characters and exiting 3:

| | before | after |
| --- | --- | --- |
| contains `Exit code: 3` | no | yes |
| length | 10,036 | 10,000 |
| truncation noted | yes, but only as a total | yes, per stream |

Five tests cover it: huge stdout with a failure, huge stderr with a failure, both
streams at once, short output unchanged, and empty output still returning
`(no output)`.

## What this does not fix

The cut is still a cut from the end. If a command prints 8,000 characters of
progress and then a two-line error to stdout, the error is inside the 10,000 and
survives; if it prints 20,000 characters first, it does not. Keeping both the head
and the tail would be a different truncation policy and a different change — this
one only stops the tool from throwing away its own conclusion.
