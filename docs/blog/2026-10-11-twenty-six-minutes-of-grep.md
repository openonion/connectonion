---
description: One grep from $HOME froze an agent for 26 minutes. Pruning the walk wasn't enough; the time went into reading 22 GB. Now the walk is lazy, pruned and capped, and big files are skipped.
tags: [Tools, Agent, Performance]
---

# Twenty-six minutes of grep

Our LinkedIn pipeline runs unattended with its working directory set to
`$HOME`, because its state lives in `~/.co`. On 2026-08-26 the model called
`grep(path="/Users/…", pattern="…")` once. The call ran for 26 minutes. The
iteration counter stayed at 1 and the phase was killed. Two weeks later the
same thing happened at iteration 43. There was no child process to look at,
just Python walking a directory tree.

We had tried prompt rules ("never grep a directory") twice. Both failed. The
model reaches for the tool because we offer it.

## The obvious fix, and the measurement

The code made the problem easy to see:

```python
files = list(base.glob("**/*"))   # every file under $HOME, then filter
```

The listing included all of `node_modules`, `Library` and every cache before
anything was filtered out. So we fixed that: `os.walk`, removing ignored
directories from the walk before it enters them, and a ceiling of 20,000
files.

Then we timed it on a real home directory, and it still didn't finish in two
minutes.

Walking turned out to be cheap. We had guessed wrong about where the time
went. The 20,000 files the walk returned took 3.4 seconds to find. They added
up to 22 GB, because 256 of them were over a megabyte: logs, exports,
databases without telling extensions. The tool reads each file whole before
matching, so the time was all in reading.

## What grep does now

A directory search walks lazily, never enters an ignored directory, skips
files over 2 MB and stops after 20,000 files, with a note saying so:

```
... search stopped after 20000 files; narrow `path` or set `file_pattern`
```

A file you name directly as `path` is still read whatever its size, so the
limit only applies when the agent hasn't said which file it wants.

The same search from `$HOME` now returns in about 20 seconds. That's still
slow, but it ends, and the note tells the model how to ask better. The tests
check that the walk never enters `node_modules`, that the ceiling produces
the note, that a huge file is skipped in a directory search and read when
named, and that `file_pattern` still filters. The first two failed on main.
