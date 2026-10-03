---
name: rem-investigate-project
description: The steps for investigating a project's page, composed after rem-investigate when the subject is under projects/.
---

# Investigating a project

Why these rules: docs/rem-skills/rem-investigate.md

- **Sessions show intent, not repository state.** What the user asked for is not
  what was built; check the files before saying anything shipped or passes.
- **Read the supplied repository snapshots, not the original checkout.** The
  page's `Paths` identify where co rem gathered evidence; they do not give this
  turn access to those directories. Start with the supplied source index,
  search for the claim in its snapshot files, and read matching entries with
  context. Cite each entry's source ID. The index names omitted files and size
  limits; an omitted body is not evidence that implementation is absent.
- A `project-inventory` item lists candidate files, not their contents. A
  directory name alone is not a project. Do not cite
  `investigation:project-inventory` in the page. Cite a retained repository
  snapshot for facts about files, or leave the fact unresolved.
- Keep an existing `Paths` value as carried notebook context without adding an
  `investigation:page` citation for that value; it has no separate original to
  open. A new path needs a retained source.
- Old files are not recent activity.
- A README or manifest establishes what a dated snapshot documents, not what
  the live system currently does. Attribute the claim to that snapshot and its
  date or revision unless current implementation or a dated user report
  confirms it. `First seen` is an observed session date, not the project's
  actual `Started` date; leave `Started` Unknown without explicit evidence.
- A workspace may contain unrelated requests. Check their actual subject before
  using them as project progress or activity; missing outcomes do not make old
  requests current pending work. A session's working directory alone does not
  bind an unnamed complaint to this project. Require a distinctive project or
  package name, component, file, version or behavior that matches the supplied
  project evidence before using a session claim. Generic release, patch, test,
  reply or package-manager requests do not identify a project. Check each claim
  against its exact source and omit ambiguous claims from the project's current
  status, insight and action.
- Audit the final `Now`, `Where it stands` and `Open threads` claims against
  each cited original before writing the candidate. A short input reporting a
  missed reply establishes that report only; it does not establish whether a
  listener is event-driven, what caused the miss, or what was implemented.
  Remove any mechanism, cause, status or next action absent from the cited
  original unless a second, separately cited source establishes it.
- For `Overview` and `Try it`, compare each step with the original source and
  with the other section. Preserve the documented order exactly; do not
  reverse prerequisite, capture, load or write steps. If the order is not
  explicit, omit `Try it` rather than inventing instructions.

## What to produce

`Facts` first (the repository remote, the stack from manifests, the first and
last session dates), then `Insight`. Three shapes, never their facts:
- `Now: stopped 2026-09-28 with the import half-merged; next the retry; blocked on review [3]`
- `Changed: moved from SQLite to files on 2026-09-02 after the lock bug [5][7]`
- `At stake: the 1 October demo needs the login, still failing [8]`

Before writing `Insight`, ask what changes a teammate's next decision. A branch
name, last commit date or list of README topics belongs in `Facts`, `Where it
stands` or `What it is`; it is not an Insight. Lead with a sourced constraint,
change or mismatch and its consequence. Put the decision-changing conclusion in
a short first sentence that fits a phone preview, then add evidence and limits.
If the packet supports none, write
`- Unknown` instead of filling the section with housekeeping.

Follow `rem-page-project`, skeleton headings exact. **`Overview` is required
when the material shows the architecture** (its parts and how work moves between
them): a closed `text` fence with arrows. Otherwise write
`Unknown — <what evidence is missing>`. An example file does not
prove an output. Current code is not a decision (local code ≠ a decision to stay
local).
Always keep the required `Open threads` heading. Write bare `Unknown` if no
current exchange is supported; do not omit the heading or invent an obligation.
