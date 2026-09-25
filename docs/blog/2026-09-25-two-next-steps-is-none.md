# Two next steps is none

Every `co` refusal ends with one line that starts `Next:`. An agent driving
the CLI reads that line and runs it; a person copies it. The rule has a test
of its own, because a refusal with no next step leaves the reader guessing.

Running the published 1.8.8b8 against a real benchmark project turned up the
opposite failure:

```
$ co benchmark check does-not-exist
Next: fix the file, then co benchmark check does-not-exist
Next: co commands
```

Two answers, and the first is wrong: there is no file to fix. The benchmark
commands print their tip on stderr so `--json` output stays parseable, and
the safety net that adds a generic `Next: co commands` to any usage error
could not see a tip it had not printed itself, so it added its own underneath.
A reader given two next steps has to decide which one the tool meant, which
is the choice the line exists to remove.

Now a command that prints its own next step tells the net so, the net stays
quiet, and a benchmark that does not exist says to create
`.co/benchmarks/<name>.yaml` rather than to fix it. The tests run the real
`co` in a subprocess and count the `Next:` lines, because counting is the
whole contract: exactly one.
