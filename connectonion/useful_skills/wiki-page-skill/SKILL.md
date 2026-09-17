---
name: wiki-page-skill
description: Canonical Wiki skill page structure shared by mapping and investigation.
---

# An installed skill's page

Use the same sections in both stages. Mapping creates missing pages and fills only observed metadata; unsupported fields stay `Unknown — not investigated yet`. Investigation edits the existing page with evidence, preserving its identity and useful prior content.

Copy headings exactly, without explanatory text on heading lines:

```markdown
# <Name>

## Source

## What it does

## When to use

## How to use

## Inputs and outputs

## Related projects

## Usage history

## Open threads

## Uncertainties

## Sources
```

Source records the original file and discovery location. Metadata describes advertised capability, not verified behavior. How to use records actual invocation, prerequisites and working directory after reading the source. Inputs and outputs records required inputs and output locations. Related projects links only observed associations. Usage history requires execution evidence; do not execute a skill merely to document it. Installed skill documentation belongs in skills/catalog/, not skills/candidates/ or skills/approved/. This template does not add skill investigation support to the person/project collector; use source-file review for this catalog.

Every investigated factual claim needs a numbered citation with a matching Sources entry, source identifier, observation date and confidence. Mark inference explicitly. Report unread or unavailable evidence in Uncertainties. Never copy facts from template examples. Preserve the runner-owned `Investigation:` line.
