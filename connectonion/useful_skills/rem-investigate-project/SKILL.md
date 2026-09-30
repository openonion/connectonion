---
name: rem-investigate-project
description: The steps for investigating a project's page, composed after rem-investigate when the subject is under projects/.
---

# Investigating a project

Why these rules: docs/rem-skills/rem-investigate.md

- **Sessions show intent, not repository state.** What the user asked for is not
  what was built; check the files before saying anything shipped or passes.
- **The page's `Paths` may be read**, offline, as evidence: inside those paths
  only, at most four levels deep and twelve relevant text files (README, docs,
  manifest, the files a claim needs). The first path is the main checkout; never
  a disposable worktree. No home directory, hidden files or credentials. Cite each
  file you read as its own source.
- A `project-inventory` item lists candidate files, not their contents. A
  directory name alone is not a project.
- Old files are not recent activity.

## What to produce

Follow `rem-page-project`, skeleton headings exact. Close the `Overview` `text`
fence, or write `Unknown — <what evidence is missing>`. An example file does not
prove an output. Current code is not a decision (local code ≠ a decision to stay
local).
