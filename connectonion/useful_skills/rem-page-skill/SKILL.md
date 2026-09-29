---
name: rem-page-skill
description: A skill page for judging usefulness, observed reliability and how to start, grounded in run evidence.
---

# An installed skill's page

Why these rules: docs/rem-skills/rem-page-skill.md

Help a reader decide: is this useful for my task, is it reliable for it, and how
do I start? Keep the opening short and understandable without company or
technical context. Link the executable source near the end; do not reproduce its
instructions as the main content.

Copy headings exactly:

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

- `What it does`: one plain sentence: the task and useful outcome. Metadata is
  advertised capability, not verified behaviour.
- `When to use`: a concrete suitable task and an important unsuitable case, when
  known. Never present invented examples as observed successes.
- `Current status`: latest observed run date, version/model, whether the task
  was completed, actual output, quality assessment, known blockers; a few lines
  linking the detailed run. With no reviewed run evidence: `Unknown — not
  verified` (not "never ran").
- `Example result`: one real artifact or short excerpt with its run reference.
  Label illustrative examples and failed/partial outputs.
- `How to use`: shortest verified invocation, prerequisites, working directory,
  ideally at most three steps. Never expose credentials.
- `Inputs and outputs`: required inputs, expected outputs and their locations.

**Run evidence and statistics**

`Usage history`: observed runs, recent first: date, task, run ID/link, skill
version or source hash, model/configuration, completion, output/artifact,
quality assessment, elapsed time, failure reason. Missing fields stay Unknown.
Exit status, task completion and quality are three separate things: a clean
exit without the artifact is not completion; an unreviewed output is not good.
Link older records when numerous.

`Performance` summarizes observed records, never advertising:

- Date range, sources, coverage gaps, number of distinct runs (deduplicated by
  run identity). No records means unknown, not 0% or zero runs.
- Completed, partial, failed, cancelled, unknown counts. A completion rate
  states numerator, denominator and exclusions; never hide failures or compare
  a truncated retry with a completed task.
- Quality separately, with a named rubric or review basis and number reviewed.
  No invented numeric score; unreviewed outputs do not pass.
- Elapsed time and input/output tokens with units and per-metric sample sizes;
  per-run totals apart from per-call usage. Never infer tokens/second from task
  duration; use generation timing. Never invent cost or token telemetry.
- Separate skill versions, models/context settings and comparable task types or
  difficulty; label cache conditions if relevant; never pool unlike runs. Small
  samples are observations, not guarantees.

**Limits and maintenance**

- `Limitations`: scope, dependencies, known failure patterns and workarounds,
  each evidenced.
- `Maintenance`: verified maintainer/contact, recent dated changes and whether
  they were validated. Earlier successes do not verify a newer version.
- `Related projects`: observed associations and valid links only.
- `Open threads`: concrete next actions, owners/dates when known.
- `Uncertainties`: missing logs, unread sources, stale results, unresolved
  identity/version attribution. Do not manufacture a complete-looking dashboard.
- `Source`: original skill file link/path and discovery location. Keep distinct
  installed copies distinct until evidence links them.
- `Sources`: numbered references with source id, date, confidence; every
  investigated claim cited. Mark inference.

**Mapping and later review**

Mapping creates missing pages from metadata, leaving unsupported sections
Unknown; reruns never overwrite existing content. Later review adds source-file
and execution evidence, adds missing sections to older pages, and preserves
identity, useful prior content and the runner-owned `Investigation:` line. Never
execute a skill merely to document it.

Catalog pages go in `skills/catalog/`, not `skills/candidates/` or
`skills/approved/`. `co rem investigate skills/catalog/<page>.md` collects
retained co eval summary records into a linked run-evidence note, without a
model or mail access; add `--eval-dir` (repeatable) for more summary
directories. It matches explicit slash-command invocation names only (not
tool-based invocation or all harnesses), and establishes neither source-version
identity nor goal achievement. Review the linked tasks, outputs and evaluations
before claiming success or verified changes; missing evidence stays unverified.
