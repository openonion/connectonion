---
name: wiki-page-project
description: Canonical Wiki project page structure shared by mapping and investigation.
---

# A project's page

Use the same sections in both stages. Mapping creates missing pages and fills only observed metadata; unsupported fields stay `Unknown — not investigated yet`. Investigation edits the existing page with evidence, preserving its identity and useful prior content.

Copy headings exactly, without explanatory text on heading lines:

```markdown
# <Name>

## Paths

## What it is

## Why it exists

## Where it stands

## How it is built

## Open threads

## Uncertainties

## Sources
```

Paths lists observed repositories, directories and worktrees. Why it exists records the user's intent. Where it stands includes an observation date; a requested change is not a completed change. Verify implementation and tests from repository evidence. Open threads names the next action, owner when known, and date. Never treat user-only coding transcripts as proof of completion.

Every investigated factual claim needs a numbered citation with a matching Sources entry, source identifier, observation date and confidence. Mark inference explicitly. Report unread or unavailable evidence in Uncertainties. Never copy facts from template examples. Preserve the runner-owned `Investigation:` line.
