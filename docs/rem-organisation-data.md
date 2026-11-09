# Organisation data for the REM reader

The full `snapshot()` records now carry the organisation list/page inputs.
The lazy Today payload stays small: the UI must load the full detail snapshot
before rendering an organisation list or page, as existing navigation does.
These are projections of notebook pages; snapshot generation does not rewrite
pages, infer employment from domains, or backfill missing facts.

| Record category | Added fields |
| --- | --- |
| `orgs` | `facts`, `kind`, `to_you`, `private`, `people`, `projects`, `obligations`, plus hierarchy fields below |
| `people` | `facts`, `units`, `organisations` (`team` is a legacy display alias of Unit) |
| `projects` | `facts`, `organisations` |

`facts` maps each canonical label to a list of
`{"value": "…", "qualifier": "…", "citations": ["1"]}`. An unknown field is
an empty list. Citation labels resolve against that record's `Sources`.
`kind`, `to_you` and the legacy `team` alias are strings, empty when unknown. Invalid kinds
remain visible in the original Facts but project to an empty filter value.
Kinds are `university`, `investor`, `client_partner`, `supplier`, `community`,
`own_company`, and `personal`.

`to_you` and Unit values retain the page language. For another display language,
read the corresponding Facts from the existing `translations[language]`
page text; these convenience strings are not independently translated.

`people`, `projects` and `organisations` contain notebook paths such as
`people/mara.md` and `orgs/fernhill.md`. Person Company and project Organisation
links support both `[[orgs/fernhill]]` (with optional `.md` and display label)
and relative Markdown links. Only existing destinations enter the projection.
An organisation's explicit `Your contacts` or `People here` links also establish
person affiliation, without changing their Company fact. Arbitrary mentions
and email domains do not establish membership. Held pages, non-person pages
and the owner are excluded from the organisation's people roster.

`obligations` reuses the grouped Today rows: `key`, `keys`, `record`, `title`,
`text`, `dir`, `since`, `due`, `quiet`, `closed`, `rank`, `section`, and any
existing reply/outcome fields permitted in that snapshot. It adds `people`,
a list of counterpart paths for name/team display. Counterparts come from
copy-page keys or an unambiguous name in the obligation. An entity obligation
can have no person counterpart. Directions are `mine`, `theirs`, or `plain`;
unknown dates are empty strings. The UI can select `mine` for what the owner
owes and `theirs` for waiting on others, using the existing Today semantics.

The list includes the organisation's own threads and its linked people's
threads. Copies share the existing resolved-source/obligation identity and
retain every original done-key in `keys`. Distinct obligations on the same
source remain distinct. Closed/skipped groups are excluded when the existing
local thread decisions mark the group closed. Quiet rows retain their flag.

`private` is true for an organisation marked `[sensitive]` or `[personal]`
outside Sources, or with `Kind: personal`. The UI must show its lock curtain
and leave relationship/body content out of the DOM until revealed. The flag
uses the existing local-reader privacy model; it does not remove the source
page text from the snapshot.

`co rem doctor` now reports missing Company-linked organisation pages and
explicit entities/shared mailboxes filed under `people/`, with a concrete fix.
It does not create, move or rewrite pages. Census excludes these non-person
records even when investigated; snapshot `service: true` exposes that decision.

## What the organisation page draws from these fields (round 6)

The organisation page (`orgPage` in `connectonion/rem/reader.html`) is a record of the
organisation, not a to-do list (owner, 2026-11-08); what you owe stays in Today. It adds
no fields and reads:

| On screen | Source | When the source is missing |
| --- | --- | --- |
| Name, kind and what it is to you | title, `kind`/`unit_kind`, `to_you` | "还不清楚是什么机构" / "还没调查" |
| Facts line | domain, roster size, unit count, first and latest dated History line, page last contact | the missing part is left out |
| Recently in touch (3 people) | each person's last contact or newest dated History line, role in unit | the block is left out |
| One link to Today | count of open `mine` obligations | no line |
| X-ray rings | `children`/`parent` (two rings; deeper units fold into their ring-2 ancestor), person `units`; size = people you know there | no units: the people form the ring |
| Ring around a unit | someone there in touch within 45 days | no ring |
| Node fill (warmth) | members' `index.relationship` mail metadata: `quiet` → cold, `trend: cooling` → cooling, `warming`/`steady`/`new` → in touch | neutral grey; legend says warmth is not known yet |
| The fuse (time line) and 最近往来 | dated `History` lines of the org and its people; one event written on two pages is shown once. A heavy line runs from the first dated exchange to today, linear in time, one tick per event; nothing on it is red | no fuse |
| Units and people (the hierarchy), who to ask | Unit, Role in unit / Role, `index.relationship.reply_seconds_them`. Units step down and to the right on a heavy elbow; every unit and person is a link in reading order | role only; no reply speed claimed |
| Unit crumb | the `parent` chain | top-level: 组织 › kind |

Not drawn because REM does not record them yet: term weeks, settled agreements, a
gave/received value ledger, renewal cycles, logos.

## Hierarchy contract (sprint9/org-hierarchy)

A unit is an ordinary `orgs/` page. **One Kind field** serves both shapes:
`ORG_KINDS` stays unchanged for top-level organisations; `UNIT_KINDS` adds
`faculty`, `school`, `department`, `course`, `team`, `programme`, `venue`, `lab`.
A unit requires one cited Parent link. The user's field enums take precedence
over the wider art-direction sketch (`company` and `member` are not added).
There is no stored depth or rollup fact.

```markdown
# 9900-F15C-CAKE

## Facts
- Kind: team [1]
- Parent: [9900](course-9900.md) [1]
- You are: client [2]

## Sources
- [1] gmail:team-introduction — 2026-11-01
- [2] gmail:client-agreement — 2026-11-02
```

`You are` is optional and cited: `client`, `incubatee`, `partner`, `alumnus`,
`casual staff`. `To you` remains the free-text organisation relationship.
People keep Company linked to the top-level organisation:

```markdown
- Company: [Fernhill University](../orgs/fernhill.md) [1]
- Unit: [9900-F15C-CAKE](../orgs/team-cake.md) [1]
- Role in unit: [9900-F15C-CAKE](../orgs/team-cake.md) — Product Owner [1]
```

Unit and Role in unit may repeat. A unit-qualified role is unambiguous even
when several memberships are listed. A bare role immediately following one
Unit link is also supported. `Team` is a read alias of Unit: upgrade renames
it; it does not create a parallel field or a unit from free text. Citations
never spill between repeated lines. Legacy free-text Unit remains visible in
Facts and the compatibility `team` string, but does not place anybody.

Each org record adds:

| Field | Shape and meaning |
| --- | --- |
| `parent` | Existing parent org path, or `""`; never more than one |
| `unit_kind` | Unit enum value or `""`; `kind` remains the top-level filter enum |
| `you_are` | Cited allowed owner relationship, otherwise `""` |
| `children` | Sorted direct child paths |
| `depth` | Root = 0; valid descendants count Parent hops; disconnected units = `null` |
| `hierarchy_issues` | Invalid/uncited/missing/multiple Parent or cycle explanations |
| `structure_source` | `"web"` if Kind/Parent cites public web structure, else `""` |
| `rollup` | `{open_owed: number, people: number, overdue: number}` across the subtree |
| `unplaced` | `{people: [person paths], obligations: [Today keys]}` lacking a specific placement |

Navigation counts top-level institutions from records with empty `unit_kind`,
not all `orgs/` pages; the generic notebook page census still counts unit pages.

A person adds `units: [{path: "orgs/team-cake.md", role: "Product Owner"}]`.
Only existing unit pages and cited Unit values qualify. Service pages, held
people and the owner do not enter member counts. `people` on an org remains
its direct roster (including its Unit links); `rollup.people` unions every
person across descendants. Explicit unit membership adds the root affiliation
to the reader's `organisations`; it never rewrites Company from a domain.

Obligations on entity pages can carry one or more cited Unit metadata lines:

```markdown
## Open threads
- The user owes Fernhill University: feedback — due 2026-11-07 [1]
  - Unit: [9900-F15C-CAKE](team-cake.md) [1]
- Fernhill University owes the user: countersigned agreement [2]
```

Each grouped obligation exposes `units: [unit paths]`. The metadata belongs
to that obligation only. Threads on a unit page are scoped there automatically;
a person's thread with exactly one known Unit can use that placement. Multiple
memberships without an explicit Unit remain unplaced. An explicit target scopes
an obligation to that node and ancestors, rather than to every unit containing
the person. `obligations` on a parent includes the deduplicated subtree, using
Today's existing identity and done/skipped decisions. `rollup.open_owed` counts
open `mine` rows, including quiet ones. `rollup.overdue` counts only `mine` rows
with a valid due date before the notebook's local day. `theirs` rows remain in
obligations for the waiting-on view. Each person and obligation counts once
per ancestor even when two descendant branches contain it.

No Parent/Unit facts leaves a flat root with `children: []`, `depth: 0` and
unplaced lists. Partial knowledge exposes known units and leaves the rest
unplaced; it never fills missing intermediate faculties or schools. Multiple
Parents, missing targets and chains leading into cycles are rejected. Valid
edges within orphan subtrees remain visible with `depth: null`.
Doctor reports malformed Parent and missing/invalid Unit links with fixes.

### Deterministic inference and writes

`org_inference.infer()` returns a **read-only plan**. Map's `reconcile()` and
accepted investigation/maintenance writes apply it under the notebook lock.
Snapshot reads never infer or write. Full team codes retain every component:
`9900-F15C-CAKE` and `9900-F13F-CAKE` are distinct units under course `9900`.
Course codes, including combined course codes and an explicitly labelled bare
course number, form course units; arbitrary numbers do not. Authored subject
metadata can establish coded unit candidates, but proves no membership or role.

Cited Role/Unit fields and subject signatures establish named chains; e.g.
`Events Coordinator | Founders Program, Division of Research & Enterprise`
creates programme → department → existing org (Division maps to department).
Sibling labels of the same kind do not establish a chain. Narrative identity
sentences can place explicit course/team codes but cannot manufacture a name
from words like “with four students per team”. Uncertain or negated assertions
are skipped. Existing affiliations/rosters select the root; domains never do.

A shared-mailbox identity creates an observed-name unit (programme when named
as such, otherwise team), never a person membership. Existing service pages
remain excluded from people; normal tidy relocates them out of `people/`.
Source IDs follow each proposed fact. Public Structure input creates units
with `web-sourced` provenance and no person membership. Different people with
the same role and team nickname but different full codes yield an evidence-
linked review question on the new unit; the codes stay separate. Existing
facts are preserved, never overwritten with inferred alternatives.

### Validation for the hierarchy change

New tests use only Fernhill University, Mara and Avery. The first tree-contract
run was red (11 failures); inference was red before its module existed.
Additional red regressions cover maintenance integration, negated claims,
repeated citation isolation, multiple Parents, sibling ambiguity, generic
mailboxes, native promotion hashes, subject candidates and narrative noise.
The final focused run passes 322 cases across hierarchy/inference, facts,
organisation data, instruction budget, fixture shape, census, Today, map and
tidy. The instruction budget remains 24,000 characters; composed owner
investigation is 23,949, person 22,992 and org 18,819. The org page skill is
7,085 characters and the person page skill is 7,887. The six-case benchmark was
authored before skill changes and passes `co benchmark check rem-org-hierarchy`;
no paid model evaluation was run.

An independent AI principal-engineer review examined backend facts, inference,
reader projections and promotion safety. It did not inspect rendered desktop
or mobile pages; the existing organisation UI still needs integration in its
own workstream. This is not a human founder review. Main-repo documentation is
updated here; carry the final fields into the Wiki/docs website with that UI.

`scripts/validation/rem_hierarchy_dry_run.py ROOT [--names]` reports candidate
counts without applying plans. The final read-only dry run proposed 22 units
(3 course, 2 department, 1 faculty, 7 programme, 1 school, 8 team), 27
memberships for 24 people, and 2 review questions. All 22 unit pages would
be new. Code rules account for 9 units / 16 people; named-unit rules account
for 13 units / 8 people. The two questions represent the same code mismatch
on its two unit pages. No web-sourced unit was proposed in this dry run. Page hashes before/after matched. This measures existing cited page
identities and authored subject metadata, not a new investigation or confirmed
structure. The owner's real notebook is read-only;
no real names or notebook material are included in test fixtures.

The final requested full-unit command completed after the last code change.
Its exact last line is:

```text
15 failed, 18489 passed, 19 skipped, 2948 warnings, 2 errors in 140.75s (0:02:20)
```

All new hierarchy/inference cases passed. The same 15 failures and two host
errors occurred in both preceding full runs. Selected reruns on untouched
branch head `bc8437a8` (with imports verified from the detached worktree)
reproduced 13 failures: schedule/default-model expectations (3), provider-error
format expectations (5), terminal styling (4), and host SIGHUP shutdown (1).
The two proactive failures and two host errors passed in that isolated baseline
run (`13 failed, 4 passed, 1 warning in 12.22s`); they remain full-run-only
results and are not claimed fixed. The full suite is not green.

The temporary baseline worktree was removed. No commits were made. Local
verification output is in `/tmp/rem-hierarchy-final-focused.log`,
`/tmp/rem-org-hierarchy-final-result.log`, and
`/tmp/rem-org-hierarchy-baseline.log`.

## Prior organisation-data validation and instruction budget


Fixtures use Fernhill Labs, Mara and Avery only. The first new regression run
failed all 13 cases. The independent AI data-contract review identified two
additional gaps (explicit student rosters and organisation-only counterpart
names); both were reproduced as two failing tests before their fixes. A final
review added coverage for all four owe/ask directions. This was a code/data
review against the design spec and mock HTML, not rendered desktop/mobile
validation. The UI layout is another builder's scope.

Character counts (Python `len(read_text())`; composed counts use `instructions`):

| Skill | Before | After |
| --- | ---: | ---: |
| `rem-page-org` | 6,022 | 6,516 |
| `rem-page-person` | 7,866 | 7,937 |
| `rem-page-project` | 8,177 | 8,333 |
| `rem-investigate-org` | 2,582 | 2,667 |

| Composed instructions | Before | After |
| --- | ---: | ---: |
| Investigate person | 22,971 | 23,042 |
| Investigate project | 21,338 | 21,494 |
| Investigate org | 17,671 | 18,250 |
| Maintain person | 17,953 | 18,024 |
| Maintain project | 18,264 | 18,420 |
| Maintain org | 16,109 | 16,603 |
| Investigate owner | 23,928 | 23,999 |

The 24,000-character budget is unchanged. The five-case behavioural benchmark
was authored at `.co/benchmarks/rem-org-data.yaml` before editing the skills;
`co benchmark check rem-org-data` validates its structure. No model evaluation
or real-notebook investigation/backfill was run.

The final focused run passed all 261 cases across `test_rem_org_data.py`,
`test_rem_facts.py`, `test_rem_instructions.py`, `test_rem_census.py`,
`test_rem_today.py`, `test_rem_tidy.py`, `test_rem_reader_model.py`, and
`test_rem_skill_eval_facts.py`.
The 21 organisation-data cases cover citation preservation, both link grammars,
private/unknown states, grouping and done decisions, doctor output, non-person
counts, student rosters and all four obligation directions. The last request
variant first failed with `dir: plain`; it now returns `mine` and the known
counterpart. The independent AI review rechecked these fixes with no remaining
material findings.

Main repository documentation is updated. Carry the field/doctor changes into
the Wiki and docs website when the organisation UI is integrated; no nested
repository changes or commits were made in this data task.

The complete requested command finished before the fixture-only correction:

```sh
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit -n 8 --dist=worksteal 2>&1 | grep -E "^FAILED|passed|failed"
```

Its exact last line was:

```text
28 failed, 18429 passed, 20 skipped, 2948 warnings in 1133.89s (0:18:53)
```

One failure was caused by the new Team schema: ten existing fictional person
benchmark pages needed `- Team: Unknown`. Those pages are now updated and
`test_every_fixture_page_is_already_in_the_facts_shape` passes in the final
261-test focused run. No production code changed after the full run. The full
suite was not repeated after this fixture-only correction.

All 28 failing cases were also run on untouched base commit `0d05b8c3` in a
temporary worktree inside this clone, with imports verified from that worktree.
24 reproduced unchanged (`24 failed, 4 passed, 1 warning in 31.77s`):

- `tests/unit/test_cli_discovery.py`: 1
- `tests/unit/test_cli_style.py`: 2
- `tests/unit/test_inbox_check_look.py`: 1
- `tests/unit/test_one_host.py`: 1
- `tests/unit/test_rem_codex_schedule.py`: 1
- `tests/unit/test_rem_collection_failure.py`: 5
- `tests/unit/test_rem_files.py`: 1
- `tests/unit/test_rem_first_run.py`: 1
- `tests/unit/test_rem_investigate.py`: 1
- `tests/unit/test_rem_map.py`: 1
- `tests/unit/test_rem_project_identity.py`: 6
- `tests/unit/test_rem_project_material.py`: 3

Three full-suite failures did not recur on either candidate or base in the
isolated rerun: `test_global_init_finishes_with_login_pending`,
`test_approve_release_uses_existing_send_path_once_and_checks_slots`, and
`test_held_local_reply_never_sends_old_words_against_a_new_version`. These
remain full-suite-only failures; the run is not claimed green.

The temporary baseline worktree was removed after verification. Local evidence
is retained in `.co/org-data-full.log`, `.co/org-data-failure-details.log`,
`.co/org-data-baseline-all-failures.log` and `.co/org-data-final-focused.log`.
The existing baseline failures and full-suite-only failures were not
changed by this organisation-data task.
