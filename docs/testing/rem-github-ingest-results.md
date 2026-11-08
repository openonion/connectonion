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
| `connectonion/rem/sessions.py` | UTC link evidence in the existing session index, printed commits (SHA + branch) only, mixed-cwd exclusion, bounded 14-day backfill instead of a format bump (see Review fixes). |
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
Eighteen failures require an ambient provider API key despite HOME isolation; the
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
- (Superseded by Review fixes, finding 2: links now need a printed SHA.) Branch evidence covers branch names actually printed in commit records; names
  seen only in requested commands do not qualify. Links establish cwd/time
  coincidence, not authorship. Remote-only library pages must declare PyPI.
- (Superseded by Review fixes: a read-only live REST smoke run was done.) No live GitHub account/PyPI smoke run was performed; acquisition was verified
  with temporary gh shims, mocked HTTPS and real local fictional Git worktrees.
- The wiki/docs-site can link the contract when the separate reader UI ships;
  neither nested site was changed or published here.

## Review fixes

The code review of `origin/main..4bb71551f` blocked this branch on eight findings.
All eight are fixed; each behavioural fix had a test that failed first.

| # | Finding | Status | Commit |
| --- | --- | --- | --- |
| 1 | A 304 broke every later sync | Fixed. `github_read()` reads the status from the `--include` headers and accepts a non-zero exit only when that status is 304. The shim now behaves like real gh (exit 1, `gh: HTTP 304`, LF status line, CRLF headers), and a 404 exit is still an error. | `234792977` |
| 2 | Session links crossed worktrees | Fixed. A link needs a SHA the session printed verbatim (`[branch sha]`), an exact repo/worktree cwd, and a commit no older than the session start. The 2 h grace is gone: the printed SHA is the evidence, and `ended` is the last reply, not the last tool output. The misnamed test is replaced by `test_worktree_session_links_only_the_commit_it_printed`. | `0ec153a52` |
| 3 | A bad Facts slug failed the whole round | Fixed. Slugs are validated when collected. An invalid one is skipped with `reason`, and its projection is `status: invalid`. | `561435da4` |
| 4 | False-positive joins | Fixed. Deploys count only on a push to the default branch (new `defaultBranchRef` in the fixed query) or on a tag push/release. Preview and staging runs are excluded, and `basis` gives the 「核对」 line the event and branch. Closing pairs use GraphQL `closingIssuesReferences` from the same repository; the join is renamed `merged_closes_open_issue`, and the UI must adopt the new name. `failed_release` needs a release/publish workflow that is not a drafter and was triggered by a tag, a release or a dispatch. A follow-up fixed `tags` being shadowed inside the release loop. | `b46bdde3b`, `5614a88b7` |
| 5 | The shared projection leaked local paths | Fixed. With `local=False`, every absolute path named by a recorded command becomes `<local repository>`, including in error text. | `c3607ffa8` |
| 6 | The legacy issue file beat a fresh cache | Fixed. A synced `.state/code` cache wins over the undated `project-issues.json`. An explicit in-memory `issues=` still wins over both. | `a2e08d6ea` |
| 7 | Cost unmeasured; the format bump forced a 180-day re-import | Fixed. Format 4 is kept. An rc61 index is backfilled only for transcripts modified in the 14-day churn window. A round starts no new repository after 90 s. Measurements are below. | `0ec153a52`, `434965ba5` |
| 8 | Low-severity items | Fixed. A refusal is `GitHubReadRefused(RuntimeError)`, so it is never cached as an error. The cooldown lives in one place (`_code_due`). `copy`, `tomllib`, `urllib`, `re`, `json`, `identity` and the project_pages imports moved to module level; only `investigate` stays lazy, because investigate imports project_pages, as five existing functions there already do. "OpenOnion key" is now "provider API key". | `8d5738acb` |

### Red first (observed before each fix)

1. With the real-gh shim: `assert cache['error'] is None` failed with
   `Command '['gh', 'api', 'repos/fernhill/lanterns/issues?…', '-H', 'If-None-Match: "cedar"']' returned non-zero exit status 1.`
2. `test_session_links_need_exact_cwd_and_a_printed_sha` failed with `AssertionError`.
   The worktree test failed with `KeyError: 'branch'`, and the session test with
   `KeyError: 'printed_commits'` (3 failed).
   The backfill test failed with `assert (2, 0) == (1, 1)`: the format bump re-imported both files.
3. `ValueError: Expected a canonical owner/repository` came out of `sync_project_repositories`.
4. `assert 12 == 4`: "Deploy preview" was taken as the latest deploy. `KeyError: 'merged_closes_open_issue'`.
   A later `failed_release` regression gave `assert [(5, ['v1.2.0'])] == [(5, …), (16, ['cedar-lights'])]`.
5. `assert '/home/mara-quill' not in …`: the `git -C` path was present in `verification` and `failed_verification`.
6. `assert 'quiet' == 'at_risk'`: the legacy `[]` overrode the cached bug issue.
7. `assert 3 == 1`: three repositories started after the budget was spent.
8. `Failed: DID NOT RAISE GitHubReadRefused`. The interim class was a ValueError, and the sync cached it as an error.

### Live smoke (read-only, public `cli/cli`, gh 2.97.0, 2026-11-08)

Only `gh api … --method GET --include`, through `github_read()`, with a fresh HOME.
Script: `<session scratchpad>/smoke/live_smoke.py` (not committed).

```text
pass 1: 9.37s {'issues': 200, 'actions/runs': 200, 'releases': 100, 'tags': 100} statuses [200, 200, 200, 200, 200, 200] calls 6
pass 2: 0.52s {'issues': 200, 'actions/runs': 200, 'releases': 100, 'tags': 100} statuses [304, 304, 304, 304, 304, 304] calls 6
guard refused ['api', 'repos/cli/cli/issues'] -> REM GitHub ingest is read-only; refused gh arguments
guard refused ['issue', 'comment'] -> REM GitHub ingest is read-only; refused gh arguments
```

All six revalidations returned real 304s, gh exited 1 on each, and the sync kept its data.
Before writing the shim I checked real gh by hand on `repos/cli/cli/tags?per_page=1&page=1`:
`exit304=1`, stderr `gh: HTTP 304`, status line ending in LF, headers in CRLF and an empty body.

GraphQL was not exercised live. Under an isolated HOME, gh cannot reach the
keychain token, so `gh auth status` fails. A full `sync_repository` therefore
recorded its GraphQL step as a cache error, with `failed_verification` showing
`[('issues', 200), ('issues', 200)]`. I did not copy the owner's token into the
isolated HOME. The PR query, including `defaultBranchRef` and
`closingIssuesReferences`, is covered only by the shim.

### Measured round wall time

Script: `<session scratchpad>/smoke/measure_round.py` (not committed). It used a
fake gh and realistic-size fictional data: 34 project pages, 200 issues of about
3 KB each, 100 PRs with 25 checks each, 200 runs, 100 tags and releases, one
matched local checkout with 300 commits in the window, and 500 session entries.

```text
round 1: 1.22s wall, synced 3 of 34 repos: {'fernhill/alder': (200, 100, 200, 'matched', None), 'fernhill/grove1': …, 'fernhill/grove10': …}
round 2: 0.62s wall, synced 3 of 34 repos: …
```

Local work is about 1.2 s per round. The network adds about 9.4 s per repository
cold (six REST reads, measured live) or 0.5 s warm, plus one GraphQL read that was
not measured. A cold round of three repositories is therefore around 30 s.
`CODE_ROUND_SECONDS = 90` stops new repositories, so the worst case is about 90 s
plus one repository's timeouts (7 × 20 s + 3 git calls), instead of three
repositories' worth. 34 repositories take 12 rounds for a first full read.

### Unit suite

The requested command, run with a fresh HOME:

```sh
env -u FORCE_COLOR uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit -n 6 --dist=worksteal
```

The suite was run from the worktree, which is itself under `/private/tmp`. It was
not run from bare `/private/tmp`, for the harness reason recorded above. On head
`5614a88b7`, with a fresh HOME and `OPENONION_API_KEY=fictional-not-a-key`, the
summary line was:

```text
18785 passed, 19 skipped, 2944 warnings in 358.43s (0:05:58)
```

The fictional key is not a credential, and nothing calls a provider. Without it,
the same command on the previous head `434965ba5` gave
`18 failed, 18767 passed, 19 skipped, 2944 warnings in 235.58s (0:03:55)`.
Seventeen of those failures were `MissingAmbientAPIKey`, and one was a subprocess
`Agent(...)` construction that needs the same key. These are the base failures
listed above, now 18 rather than 19 because the SIGHUP case passed. All eight
affected files pass with the fictional key: `128 passed, 1 skipped`.
