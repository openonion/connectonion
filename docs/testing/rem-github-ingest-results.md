# REM GitHub ingest results

Branch: `sprint11/github-ingest`; base: `971c7991e` (rc61).
Implementation and tests use fictional repositories/contributors only. Every shell
invocation used a fresh HOME, inherited by its subprocesses. No real home `.co`
was read or modified, no credentials were loaded, and no branch was pushed.

## Commits

- `fcbe8c848` — Specify the bounded REM repository ingest contract.
- `0e7beb21e` — Ingest bounded repository evidence for REM project pages.
- `d79cc20ce` — Keep green age unknown when check contexts are truncated.
- `46d186a77` — Retain remote evidence for project folders without Git metadata.
- This report is committed separately as “Record REM GitHub ingest verification results.”

## Changed files and purpose

| File | Purpose |
| --- | --- |
| `connectonion/rem/project_pages.py` | Closed read-only gh argv guard, bounded API/ETag cache, cooldown/error preservation, local repo identity and churn, exact session links, PyPI reads, three-repo round refresh. |
| `connectonion/rem/project_data.py` | Cache-only repository JSON projection, six deterministic joins with command/time provenance, cached-issue fallback for existing scoring, shared-session-link omission. |
| `connectonion/rem/native_round.py` | One model-free repository refresh per consented native round under the existing lock. |
| `connectonion/rem/sessions.py` | UTC link evidence in the existing session index, printed branches only, mixed-cwd exclusion, one-time session format refresh. |
| `tests/unit/test_rem_github_ingest.py` | Temporary PATH gh shim, absolute HOME isolation, guard rejection, caps, cooldown, ETags, errors, joins, churn/worktrees, package reads and regression boundaries. |
| `tests/unit/test_rem_sessions.py` | Imported session evidence rejects changed cwd and excludes branch names that were merely requested. |
| `docs/rem-project-data.md` | Fields, caps, cache shape/path, guard, link rule, provenance and one fictional projection example for the separate UI builder. |
| `docs/testing/rem-github-ingest-results.md` | This verification record and limitations. |

No changes to `reader.html`. The local implementation plan was maintained in the
repository's ignored `IMPLEMENTATION_PLAN.md`; no new persistent store/database
was introduced.

## Red-first observations

1. Initial contract run: `8 failed in 2.25s` — missing `github_read`,
   `sync_repository`, and `session_commit_links` attributes, before implementation.
2. Independent-review regressions failed before fixes: missing cached issue URL
   (`KeyError: 'url'`), unrelated local repository incorrectly receiving churn,
   and sampled successful checks incorrectly proving a PENDING PR green.
3. A SUCCESS rollup with `checksTruncated: true` initially still yielded a
   two-hour green age: `1 failed, 18 deselected in 2.26s`. It now yields no age.
4. An ordinary non-Git project folder initially turned successful GitHub reads
   into a packet error: `1 failed, 19 deselected in 44.03s`. The regression
   failed before the Git-root precheck.
5. A first cap test failure was a fixture defect: its second page always returned
   empty. The shim now implements real 100-item page slices; the test verifies
   stopping at 200 issues, 100 PRs and 200 runs without exhausting the fixture.

Targeted verification after review fixes:

```text
229 passed in 9.43s
```

That targeted run preceded the final non-Git-folder regression, which is included
in the final full run below. The clean targeted rerun also included the three
source-inspection test files affected by obsolete bytecode:

```text
281 passed in 78.28s (0:01:18)
```

## Full unit verification

Requested command:

```sh
env -u FORCE_COLOR uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit -n 6 --dist=worksteal
```

The first literal `/private/tmp` attempt used a temporary `tests` symlink,
`UV_PROJECT`/`PYTHONPATH` pointing to this worktree, and fresh HOME. It did not
load the worktree pytest.ini and the existing
`_no_stray_project_above_the_test` fixture rejects `/private/tmp` as cwd: the
resolved project is neither the repository nor the test's own temporary folder.
This invalid run was interrupted; its exact summary was:

```text
21 failed, 6830 passed, 11 skipped, 1689 warnings, 6496 errors in 57.16s
```

The temporary tests symlink was removed. No shared `.co` was removed or changed.
The same requested command was then run from the worktree with fresh HOME and
its normal pytest configuration. First complete result:

```text
19 failed, 18752 passed, 19 skipped, 2944 warnings in 187.82s (0:03:07)
```

A subsequent full run after the last regressions/fixes completed with:

```text
26 failed, 18751 passed, 19 skipped, 2944 warnings in 453.15s (0:07:33)
```

Seven additional failures were a verification setup mistake: pytest bytecode
created by the literal `/private/tmp/tests` symlink attempt retained that source
path after the temporary link was removed. Source-inspection tests could no
longer read their own functions. Only the 794 generated test `.pyc` files whose
embedded source filename began `/private/tmp/tests/` were removed; no application
code or test assertion was changed. The clean rerun below uses canonical paths.

Final complete result after generated bytecode cleanup:

```text
19 failed, 18758 passed, 19 skipped, 2944 warnings in 549.24s (0:09:09)
```

The final full run has exactly the same 19 failing test cases as the base
comparison (verified by comparing failure-name sets). All new ingest regressions
passed.

The 19 failures were independently reproduced on unchanged base `971c7991e`,
using a detached temporary baseline worktree and the same Python environment
with its bin directory on PATH and baseline source on PYTHONPATH:

```text
19 failed, 124 passed, 1 skipped in 22.58s
```

Baseline coverage comprised all files containing the original failing tests:
`test_shell_tool.py`, `test_github_action.py`, `test_co_ai_hosts_a_factory.py`,
`test_admin_logs_reads_the_log_the_agent_writes.py`, `test_agent_index.py`,
`test_the_host_quick_start_runs.py`,
`test_the_session_history_belongs_to_the_project.py`,
`test_what_the_agent_serves_comes_from_the_project.py`, and `test_one_host.py`.
Eighteen failures require an ambient OpenOnion key despite HOME isolation; the
SIGHUP host-stop case times out. This branch does not change those subsystems or
weaken their tests. A passing whole-suite result is not claimed.

## Independent review and deviations

A separate AI reviewer examined the Python/data contract, identified significant
issues, and rechecked their fixes. Repository identity, cached issue scoring,
complete-check green age, mixed-cwd session attribution, deploy completion cutoff
and non-Git directory handling were rechecked. No significant finding remained
within that review scope. This was not a human founder review or a rendered-page
review; the UI belongs to another branch.

Deviations/limits:

- The complete configured suite must run from the worktree because the existing
  test harness rejects the requested shared `/private/tmp` cwd. The literal
  attempt and its failure are recorded above.
- The full suite retains the 19 reproduced base failures; no real credential
  bootstrap was attempted to make credential-dependent tests pass.
- Deploy completion uses the concluded run's `updated_at` as a conservative upper
  bound. Green age is omitted when check context coverage is truncated.
- Releases/tags are capped at 100, local history at 1,000 commits/14 days, PyPI
  responses at 4 MB, and repository sync at three due repos per round. Samples
  and absence from them do not prove a complete clean repository.
- Branch evidence covers branch names actually printed in commit records; names
  seen only in requested commands do not qualify. Links establish cwd/time
  coincidence, not authorship. Remote-only library pages must declare PyPI.
- No live GitHub account/PyPI smoke run was performed; acquisition was verified
  with temporary gh shims, mocked HTTPS and real local fictional Git worktrees.
- The wiki/docs-site can link the contract when the separate reader UI ships;
  neither nested site was changed or published here.
