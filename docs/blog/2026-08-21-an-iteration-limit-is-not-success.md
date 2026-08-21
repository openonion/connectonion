# The pipeline that succeeded without doing the work

Four agent jobs ran in sequence overnight. The first was supposed to finish a
LinkedIn workflow before the next job started. It did not finish: the Agent
used every allowed iteration and printed `Task incomplete`. The shell saw exit
zero, marked the step green, and launched the other three anyway.

By morning, the run log looked healthy. Only the English sentence buried in
stdout revealed that the first job had stopped halfway through. The later jobs
had inherited an assumption that was never true, and the scheduler had no
signal it could use to halt or retry. Raising the iteration limit made the run
more expensive, but did not make that signal any more honest.

The important turn was realizing that the partial answer was not the problem.
It was useful evidence and, for a resumable session, worth preserving. The lie
was the process status. We changed one-shot execution so it commits the partial
session and prints the result, then exits nonzero when the terminal reason is
`max_iterations`. JSON mode makes the same distinction explicit:

```json
{"session_id":"...","result":"...","outcome":"max_iterations","error":null}
```

A naturally completed turn reports `outcome: "natural"` and exits zero; an
execution failure reports `outcome: "error"`. An orchestrator can now stop,
alert, or resume based on data instead of grepping prose.

The lesson was smaller than a new budgeting system: a safety limit is not a
success criterion. Cost ceilings and in-context budget guidance need their own
design, but no future budget feature can compensate for reporting unfinished
work as green.
