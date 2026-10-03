---
name: rem-investigate-project
description: The steps for investigating a project's page, composed after rem-investigate when the subject is under projects/.
---

# Investigating a project

Why these rules: docs/rem-skills/rem-investigate.md

- **Sessions show intent, not repository state.** Check files before claiming
  anything shipped or passed.
- **Inspect the live repository paths supplied in the task.** Start with the
  evidence index and mapped paths. Use `git log`, `git show`, `README.md`,
  `pyproject.toml`, `package.json` and relevant source files to verify claims.
  Record the inspected path and revision or timestamp in each source
  citation. For a live file outside snapshots, cite
  `file:/absolute/path@<sha256>` (hash full bytes with `shasum -a 256`)
  so the cited version can be retained. An omitted index body is not proof
  that implementation is absent.
- Files outside mapped `Paths` cannot support this page, even with a valid
  hash. Use `Unknown` without an inspectable original under mapped paths.
- `project-inventory` names files, not contents; cite inspected originals,
  never `investigation:project-inventory`.
- Keep existing `Paths` without citing `investigation:page`. A new path needs
  a retained source.
- Put search-window limits in your final reply, not page `Uncertainties` or
  `Sources`; `investigation:coverage` is not citable project evidence.
- With zero assigned session inputs, keep `Insight` and `Open threads` bare
  `Unknown`. Dated repo notes may explain history, not current user work.
  `project-input-scope` is not a citable original.
- Old files are not recent activity. Attribute README/manifest claims to their
  snapshot date or revision unless current code or a dated user report confirms
  them. `First seen` is an observed session, not project `Started`; leave
  `Started` Unknown without explicit evidence.
- `Status` and `Last activity` need dated evidence of progress, not a branch
  or commit timestamp. A checkout snapshot belongs in `Where it stands`,
  not as proof of a current task or next step.
- Cwd alone does not assign a request to this project. Match a distinctive
  project, package, file, version or behavior; omit generic or old requests
  with no verified outcome from status, insight and action.
- Assign unnamed follow-ups only when an earlier supplied input in that
  session establishes this project. Otherwise leave them unassigned.
- Audit every concrete claim in `Insight`, `What it is`, `Why it exists`,
  `Where it stands` and `Open threads` against its adjacent cited original
  before writing the candidate. A question about a filter proves only that
  the user asked; a request to organize files does not authorize a commit or
  push. Data collection does not prove assessment, outreach or a product goal;
  saving a crawler does not prove it resumes. A short input reporting a
  missed reply or continued process establishes that report only; it does not
  prove a prior stop request, an event-driven listener, a cause, or a separate
  browser failure.
  Remove any mechanism, cause, status or next action absent from the cited
  original unless a second, separately cited source establishes it.
- A source comment about a test is not a verified run; require a run log for
  a current test outcome.
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
Do not put a “no confirmed pending work” summary under this heading as a
thread; it would appear as an open task in the reader.
