# Why rem-abstract says what it says

The rules live in `connectonion/useful_skills/rem-abstract/SKILL.md`. This
file holds the reasons and measurements behind them; it is not loaded at
runtime (#1851).

## Pages, never sources

Reaching for the original mail or session in this stage is how a decision page
becomes a transcript. The split is also checked in code: `instructions("abstract",
"codex")` equals `instructions("abstract")`, because a stage that reads pages has
no business knowing which store they came from.

## Why the lifts run in order

A principle is not a thing anyone ever said, so it cannot be written until the
decisions it abstracts exist.

## Most of what you read is not a decision

Measured on a real repository: of 400 merged pull requests in five weeks, about
30 carry the "was an alternative rejected?" signal.

On a notebook trial, eight rounds read 159 captured lines and wrote 77 pages,
but 75 of 83 lines reported as left had no passing page; most sampled lines
were instructions or questions without a rejected alternative. Discarding and
merging were correct abstraction work that the queue mistook for failure.
Stable line IDs and explicit report verdicts now distinguish those completed
outcomes from refused pages and missing answers. A merge names a decision page
that passed this round; it cannot hide a refused or unwritten page.

The task names its report at `.state/tasks/abstract-<id>/report.md`, beside
`instructions.md`, outside the output notebook. Both that file and the final
message feed the same verdict checks and are saved together in `result.json`
before cleanup removes the report file. Previously only the final message
was read: a reply linking to a report lost every verdict held only in the file.
Links without verdict lines still leave the captured line unanswered.

## `## Why` is load-bearing

A decision page that records only what was chosen grows nothing above it; the
reasons are the raw material of the principles lift.

## Grouping by the reason

A principle is never stated once, in any source, which is why it cannot be
extracted from one. Three real decisions from a single day, grouped by reason
rather than topic:

```
calendar triggers did not fire      → measured three times, changed to a tick
account/read answered null          → measured, read the credential instead
-c mcp_servers={} left servers on   → measured, gave it an empty CODEX_HOME
                                      ↓
        Do not trust an API's report of itself; measure the behaviour.
```

## Three decisions minimum

Two is a coincidence and one is an opinion; a page written from either is a
one-off dressed up as a rule. Naming the decisions lets a reader check the
abstraction rather than believe it. A notebook with one principle per decision
has none.

## No `agenda/` or `opportunities/`

Both are computed from Open threads and state on entity pages. Writing them in
this stage creates the same commitment twice, in two wordings.

## Knowledge lift: after decisions, before principles

The three lifts run in order: decisions, knowledge, principles. A knowledge page
records learning that holds beyond one decision: how something works, what went
wrong and why, or a method that worked. It draws from at least two notebook pages
in `decisions/`, `sessions/` or `projects/`, named under `## Drawn from`.
Principles still require three decisions; knowledge does not replace that rule.

Investigate describes a subject from raw sources. Abstract learns from settled
notebook experience. Abstract may create a knowledge page or append a clearly
headed section to an existing one; it cannot rewrite, replace or delete any
existing knowledge text, including Investigate's topic pages. Existing titles,
sections and source definitions stay exactly as written. An appended section
uses `### Sources` and fresh citation numbers for its new evidence.

The decision quote rule also applies here: copy the owner's verbatim words into
the body immediately followed by `[n]`, define each original source ID under
`## Sources`, and keep the originating page path as context. Do not reopen raw
sources or turn a paraphrase into a quote. For example:

```markdown
# Checking whether a scheduled job actually ran

A saved schedule does not show whether the job ran. Check a run receipt after
the due time; in the trial a tick worked after calendar triggers failed.
“The calendar trigger never fired; the interval tick did.” [1]
“Check the run receipt after the due time.” [2]

## Drawn from
- [Scheduling trigger choice](../decisions/scheduling-trigger.md)
- [Scheduler trial](../projects/scheduler-trial.md)

## Sources
- [1] codex:schedule:12 — originating page: `decisions/scheduling-trigger.md`.
- [2] codex:trial:31 — originating page: `projects/scheduler-trial.md`.
```
