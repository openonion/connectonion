# Organisation data for the REM reader

The full `snapshot()` records now carry the organisation list/page inputs.
The lazy Today payload stays small: the UI must load the full detail snapshot
before rendering an organisation list or page, as existing navigation does.
These are projections of notebook pages; snapshot generation does not rewrite
pages, infer employment from domains, or backfill missing facts.

| Record category | Added fields |
| --- | --- |
| `orgs` | `facts`, `kind`, `to_you`, `private`, `people`, `projects`, `obligations` |
| `people` | `facts`, `team`, `organisations` |
| `projects` | `facts`, `organisations` |

`facts` maps each canonical label to a list of
`{"value": "…", "qualifier": "…", "citations": ["1"]}`. An unknown field is
an empty list. Citation labels resolve against that record's `Sources`.
`kind`, `to_you` and `team` are strings, empty when unknown. Invalid kinds
remain visible in the original Facts but project to an empty filter value.
Kinds are `university`, `investor`, `client_partner`, `supplier`, `community`,
`own_company`, and `personal`.

`to_you` and `team` retain the page language. For another display language,
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

## Validation and instruction budget

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
