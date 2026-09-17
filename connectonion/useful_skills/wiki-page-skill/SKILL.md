---
name: wiki-page-skill
description: A skill page for judging usefulness, observed reliability and how to start, grounded in run evidence.
---

# An installed skill's page

Help a reader decide: is this useful for my task, is it reliable for that task,
and how do I start? Keep the opening short and understandable without prior
company or technical context. This remains a skill page; the first-time reader
is a design test, not a separate onboarding page. Link the executable source
near the end instead of reproducing its instructions as the main content.

Copy headings exactly. Mapping and later evidence review use the same structure:

```markdown
# <Name>

## What it does

## When to use

## Current status

## Example result

## How to use

## Inputs and outputs

## Usage history

## Performance

## Limitations

## Maintenance

## Related projects

## Open threads

## Uncertainties

## Source

## Sources
```

**The short opening**

- `What it does`: one plain-language sentence stating the task and useful outcome.
  Metadata describes advertised capability, not verified behavior.
- `When to use`: a concrete suitable task and an important unsuitable case, when
  known. Do not present invented examples as observed successes.
- `Current status`: latest observed run date, version/model, whether the requested
  task was completed, the actual output, quality assessment and known blockers.
  Summarize in a few lines and link the detailed run. If no run evidence has been
  reviewed, say `Unknown — not verified`; this does not mean it has never run.
- `Example result`: one useful real artifact or a short excerpt with its run
  reference. Label illustrative examples and failed/partial outputs explicitly.
- `How to use`: the shortest verified invocation, prerequisites and required
  working directory, ideally at most three steps. Do not expose credentials.
- `Inputs and outputs`: required inputs, expected outputs and their locations.

**Run evidence and statistics**

`Usage history` is a recent-first record of observed runs. Record date, task,
source run ID/link, skill version or source hash, model/configuration, task
completion, output/artifact, quality assessment, elapsed time and failure reason
when available. Missing fields stay Unknown. Process exit status and task
completion are separate: a clean exit without the requested artifact is not a
completed task. Quality is a third dimension, based on stated checks or review;
an unreviewed output is not automatically good. Link older records when numerous.

`Performance` summarizes observed records, not advertising claims:

- State the date range, sources, coverage gaps and number of distinct runs.
  Deduplicate repeated logs by run identity. No available records means unknown,
  not a 0% completion rate or proof of zero executions.
- Show completed, partial, failed, cancelled and unknown counts. For a completion
  rate, explicitly state numerator, denominator and excluded records; do not hide
  failures or compare a truncated retry with a completed task.
- Assess output quality separately with a named rubric or review basis and the
  number reviewed. Do not invent a numeric quality score or count unreviewed
  outputs as passing.
- Report observed elapsed time and input/output token counts with units and
  per-metric sample sizes. Distinguish per-run totals from per-call usage. Never
  infer tokens per second from total task duration; use generation timing when
  available. Do not invent provider cost or token telemetry.
- Separate skill versions, models/context settings and comparable task types or
  difficulty. Label cache conditions if relevant; do not pool unlike runs into
  a misleading model comparison. Small samples are observations, not guarantees.

**Limits and maintenance**

- `Limitations`: supported scope, dependencies, known failure patterns and
  workarounds, each backed by evidence.
- `Maintenance`: verified maintainer/contact when known, recent changes and their
  dates, and whether those changes were validated. Earlier successful runs do
  not verify a newer version.
- `Related projects`: only observed project associations and valid links.
- `Open threads`: concrete next actions and owners/dates when known.
- `Uncertainties`: missing logs, unread sources, stale results and unresolved
  identity/version attribution. Keep these visible rather than manufacturing
  a complete-looking performance dashboard.
- `Source`: original skill file link/path and discovery location. Preserve the
  distinct identity of different installed copies until evidence links them.
- `Sources`: numbered references with source identifier, date and confidence.
  Every investigated factual claim needs a matching reference. Mark inference.

**Mapping and later review**

Mapping creates missing pages from metadata and leaves unsupported sections
Unknown. Later review adds source-file and execution evidence while preserving
identity, useful prior content and the runner-owned `Investigation:` line. Add
missing sections when reviewing older pages; mapping reruns do not overwrite
existing content. Never execute a skill merely to document it.

Catalog pages belong in `skills/catalog/`, not `skills/candidates/` or
`skills/approved/`. `co wiki investigate skills/catalog/<page>.md` now collects retained co eval
summary records into a linked run-evidence note without a model or mail access.
Use repeatable `--eval-dir` flags for additional summary directories. It matches
explicit slash-command invocation names, not tool-based invocation or all harnesses;
it does not establish source-version identity or evaluate goal achievement.
Review the linked tasks, outputs and recorded evaluations before claiming success
or verified changes. Missing evidence remains unverified.
