---
name: wiki-page-project
description: Canonical Wiki project page structure shared by mapping and investigation.
---

# A project's page

Use the same sections in both stages. Mapping creates missing pages and fills only observed metadata; unsupported fields stay `Unknown — not investigated yet`. Investigation edits the existing page with evidence, preserving its identity and useful prior content.

Copy headings exactly, without explanatory text on heading lines:

```markdown
# <Name>

## Architecture map

## Paths

## What it is

## Why it exists

## Where it stands

## How it is built

## Latest issues

## Open threads

## Uncertainties

## Sources
```

Paths lists observed repositories, directories and worktrees. Why it exists records the user's intent. Where it stands includes an observation date; a requested change is not a completed change. Verify implementation and tests from repository evidence. Open threads names the next action, owner when known, and date. Never treat user-only coding transcripts as proof of completion.

Every investigated factual claim needs a numbered citation with a matching Sources entry, source identifier, observation date and confidence. Mark inference explicitly. Report unread or unavailable evidence in Uncertainties. Never copy facts from template examples. Preserve the runner-owned `Investigation:` line.

**Filling the architecture and issues sections**

`Architecture map` is the first section directly below the project title, giving
a visual overview before the detailed prose. It contains a fenced `text` block with an ASCII diagram of the
observed modules and their connections or data flow. Add a compact directory
tree when it helps locate those modules. Label arrows and explain the main
entry point in prose. Cite the inspected repository paths and revision/date
outside the diagram. Distinguish proposed structure from implemented structure;
do not invent a diagram from the project's name. During mapping, leave this
section Unknown until repository evidence has been inspected.

`Latest issues` lists recent concrete bugs, regressions and blockers, newest
first. Each entry records the observation date, symptom, affected component or
user impact, current status, and evidence. Include the next diagnostic step or
an existing issue link when known. A user report is a reported problem, not a
verified diagnosis. Do not mark an issue resolved from a proposed fix alone.
If none were found, state the checked sources and date rather than asserting
that the project has no issues. `Open threads` remains the broader action list;
refer to issue entries instead of duplicating their full descriptions.

When updating older project pages, add these missing sections while preserving
existing content. Re-running mapping does not overwrite existing pages.
