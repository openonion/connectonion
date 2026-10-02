---
name: rem-page-skill
description: A skill page for judging usefulness, observed reliability and how to start, grounded in run evidence.
---

# An installed skill's page

Why these rules: docs/rem-skills/rem-page-skill.md

Help a reader choose a task, judge reliability and start. Keep the opening
short and plain. Link the source near the end; do not paste its instructions.
State missing execution evidence once in `Current status`; do not repeat it in
every section. Omit optional sections that would only restate that gap.

Keep the core headings `What it does`, `Insight`, `When to use`, `Current status`,
`How to use`, `Inputs and outputs`, `Usage history`, `Limitations`, `Uncertainties`,
`Source` and `Sources`. Keep other headings only when evidence fills them; omit
an optional section whose whole body would be Unknown. Keep the order below:

```markdown
# <Name>

## What it does

## Insight

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

- `Insight`: 1–3 cited findings changing task choice, setup or verification.
  Compare instructions with recorded outputs; name the mismatch, capability or
  failure condition, consequence and next check. Prefer a specific trap or
  conflicting rule over listing prerequisites. Put the execution-evidence
  caveat in `Current status`, not in each Insight. Counts do not prove success.
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
- Notebook links use notebook paths. Do not copy source-relative
  `../name/SKILL.md` links into the catalog; use a verified catalog link or
  the plain skill name.
- `Open threads`: concrete next actions, owners/dates when known.
- `Uncertainties`: missing logs, unread sources, stale results, unresolved
  identity/version attribution. Do not manufacture a complete-looking dashboard.
- `Source`: the map owns it: the source file (linked, never pasted), discovery
  location, allowed tools and every installed copy, identical or differing by
  content hash. Leave it as the map wrote it.
- `Sources`: numbered references with source id, date, confidence; every
  investigated claim cited. Mark inference.

**Mapping and later review**

Mapping owns installed copies and session counts. Review adds evidence and
preserves those markers, identity, useful prior content and `Investigation:`.
Never execute a skill merely to document it.

Catalog pages go in `skills/catalog/`. Review source and retained eval summaries;
never read mail or execute the skill for this review.
Only explicit slash-command records are matched; attribution to an installed
version and goal achievement stay unverified without artifact evidence.
