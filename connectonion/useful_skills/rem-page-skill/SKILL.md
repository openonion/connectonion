---
name: rem-page-skill
description: A skill page for judging usefulness, observed reliability and how to start, grounded in run evidence.
---

# An installed skill's page

Help a reader choose and start a task. Keep the lead short; link, don't paste,
the source. State missing execution evidence once in `Current status`.
Keep `#` title exactly the mapped invocation name, without a descriptive suffix;
`co rem investigate` uses it to find the skill's runs.

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
- `What it does`: one plain sentence: the task and intended outcome. Say the
  skill aims to produce checked work until an openable artifact proves it did.
- `When to use`: a concrete suitable task and an important unsuitable case, when
  known. Never present invented examples as observed successes.
- `Current status`: latest observed run date, version/model, whether the task
  was completed, actual output, quality assessment, known blockers; a few lines
  linking the detailed run. With no reviewed run evidence: `Unknown — not
  verified` (not "never ran").
- `Example result`: a retained, openable artifact or excerpt with its run
  reference. If only a run report survives, label its output as reported;
  leave uninspected artifact details Unknown. Label partial results.
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
- Separate versions, models/context and task types/difficulty; label cache
  conditions. Never pool unlike runs. Small samples are not guarantees.

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

Mapping owns installed copies, usage and identity; preserve them and
`Investigation:`. Catalog pages stay under `skills/catalog/`; never run the skill.
Eval counts /skill inputs, while sessions also include file loads. Neither
proves installed version or goal achievement without artifacts.

Match claims to exact tasks and originals; cite snapshot IDs. Treat handbacks
as reports until artifact review.
Open threads need a current, source-backed pending request.
