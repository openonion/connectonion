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
  Cite the exact supplied `source` ID, usually `project-source:` or `codex:`.
  `origin: git:`, command output, paths and revisions are not source IDs.
  Omit unsupported claims. For a new live file, first confirm its exact path
  exists with `test -f`, then hash those bytes with `shasum -a 256` and cite
  `file:/absolute/path@<sha256>`. A `git show` path is historical, not a live
  file. An omitted index body is not proof
  that implementation is absent.
- Files outside mapped `Paths` cannot support this page, even with a valid
  hash. Use `Unknown` without an inspectable original under mapped paths.
- `project-inventory` names files, not contents; cite inspected originals,
  never `investigation:project-inventory`.
- Keep existing `Paths` and its `Sessions`, `First seen`, and `Last seen`
  mapping lines exactly. These are source routing, not project evidence;
  do not cite `investigation:page`. A new path needs a retained source.
- Put search-window limits in your final reply, not page `Uncertainties` or
  `Sources`; `investigation:coverage` is not citable project evidence.
- With zero assigned session inputs, keep `Insight` and `Open threads` bare
  `Unknown`. Dated repo notes may explain history, not current user work.
  `project-input-scope` is not a citable original.
- Old files are not recent activity. Attribute README/manifest claims to their
  snapshot date or revision unless current code or a dated user report confirms
  them. `First seen` is an observed session, not project `Started`; leave
  `Started` Unknown without explicit evidence.
- `Status` and `Last activity` need dated progress, not a branch or commit
  timestamp. If later requests follow the last verified progress, do not call
  the older progress the last activity; say when the last request was and leave
  actual current progress Unknown. A checkout snapshot is not a next step.
- Cwd alone does not assign a request here. Match a distinctive project, file,
  version or behavior; omit generic or old requests from current status.
- A newer subfolder link does not prove older requests describe it. Keep the
  link and older requests distinct; their connection is unverified without an
  original that joins them.
- Assign unnamed follow-ups only when an earlier supplied input in that
  session establishes this project. Otherwise leave them unassigned.
- Audit every concrete claim in `Insight`, `What it is`, `Why it exists`,
  `Where it stands` and `Open threads` against its adjacent cited original
  before writing. A question proves only an ask; collection does not prove
  assessment, outreach or purpose; a saved crawler need not resume. Reports
  do not prove their cause or listener, and a domain does not prove
  `Organisation`. Frame requests as goals. Remove unsupported claims.
- An organization request does not authorize a commit. A later generic "you
  can commit and push" proves permission, not its target without adjacent
  context. A message left for someone does not prove delivery or receipt.
- Keep actors and actions exact: "professional Airbnb hosts; ask the owner"
  does not mean professionally managed homes or calling agents. For a table,
  verify the row's scope and action cell; a clipped row cannot prove a filter.
  Preserve the source's noun: houses or property listings are not necessarily
  rental listings.
- A source comment about a test is not a verified run; require a run log for
  a current test outcome.
- For `Overview` and `Try it`, compare each step with the original source and
  with the other section. Preserve the documented order exactly; do not
  reverse prerequisite, capture, load or write steps. If the order is not
  explicit, omit `Try it` rather than inventing instructions.

## What to produce

`Facts` first (remote, stack from manifests, dated sessions), then a short
source-backed `Insight` using `Now:`, `Changed:` or `At stake:`.

`Insight` should change a teammate's next decision. A branch, commit date or
README topic belongs elsewhere. Lead with a sourced constraint or change and
its consequence in one phone-length sentence, then add evidence and limits.
`Now:` needs the latest supported constraint, not older progress after newer
requests. If the packet supports none, write
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
