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
- A workspace may contain unrelated requests. Check their actual subject before
  using them as project progress or activity; missing outcomes do not make old
  requests current pending work. Check each claim against its exact source.

## What to produce

`Facts` first (the repository remote, the stack from manifests, the first and
last session dates), then `Insight`. Three shapes, never their facts:
- `Now: stopped 2026-09-28 with the import half-merged; next the retry; blocked on review [3]`
- `Changed: moved from SQLite to files on 2026-09-02 after the lock bug [5][7]`
- `At stake: the 1 October demo needs the login, still failing [8]`

Follow `rem-page-project`, skeleton headings exact. **`Overview` is required
when the material shows the architecture** (its parts and how work moves between
them): a closed `text` fence with arrows. Otherwise write
`Unknown — <what evidence is missing>`. An example file does not
prove an output. Current code is not a decision (local code ≠ a decision to stay
local).
