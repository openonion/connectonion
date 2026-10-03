---
name: rem-investigate-project
description: The steps for investigating a project's page, composed after rem-investigate when the subject is under projects/.
---

# Investigating a project

Why these rules: docs/rem-skills/rem-investigate.md

- **Sessions show intent, not repository state.** Check files before claiming
  anything shipped or passed.
- **Read the supplied repository snapshots, not the original checkout.** The
  page's `Paths` identify where co rem gathered evidence; they do not give this
  turn access to those directories. Start with the supplied source index,
  search for the claim in its snapshot files, and read matching entries with
  context. Cite each entry's source ID. The index names omitted files and size
  limits; an omitted body is not evidence that implementation is absent.
- `project-inventory` lists candidate files, not their contents. Do not cite
  `investigation:project-inventory`; cite a retained snapshot for file facts.
- Keep existing `Paths` without citing `investigation:page`. A new path needs
  a retained source.
- Put search-window limits in your final reply, not page `Uncertainties` or
  `Sources`; `investigation:coverage` is not citable project evidence.
- If the `project-input-scope` item says zero session inputs were assigned,
  keep `Insight` and `Open threads` as bare `Unknown`. Dated repository notes
  can explain the project and its history in `What it is` and `Where it
  stands`; they do not establish current user work or a live next action.
  The scope item is not an original and must not appear in `Sources`.
- Old files are not recent activity. Attribute README/manifest claims to their
  snapshot date or revision unless current code or a dated user report confirms
  them. `First seen` is an observed session, not project `Started`; leave
  `Started` Unknown without explicit evidence.
- `Status` and `Last activity` mean demonstrated project progress, not a Git
  branch or commit timestamp. Put a branch or commit in `Where it stands` as a
  dated checkout snapshot; leave those Facts Unknown unless a dated original
  ties actual work to this project. A commit alone does not establish the
  user's current task or next step.
- A workspace holds unrelated requests. An old request with no outcome is not
  necessarily pending. Cwd does not identify the subject. Require a distinctive
  project, package, component, file, version or behavior match to the supplied
  project evidence. Generic release, patch, test, reply or package-manager
  requests do not identify a project. Omit ambiguous status, insight and action.
- Assign unnamed follow-ups only when an earlier supplied input in the same
  session establishes this project's subject. If it names another product, or
  was not supplied, leave the follow-up unassigned despite its cwd. Exclude it
  from current findings, status, activity, issues, threads and next action.
- Audit the final `Now`, `Where it stands` and `Open threads` claims against
  each cited original before writing the candidate. A short input reporting a
  missed reply establishes that report only; it does not establish whether a
  listener is event-driven, what caused the miss, or what was implemented.
  Remove any mechanism, cause, status or next action absent from the cited
  original unless a second, separately cited source establishes it.
- A comment in source code reporting a test is a dated source note, not an
  independently verified execution result. Attribute it to the file and date;
  do not call it the latest run or a current outcome without a run log or
  another dated original that verifies that claim.
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
