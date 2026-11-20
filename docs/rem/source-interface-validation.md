# Shared source prerequisite: scope and validation

**Current status: the author has run the updated checks after the review fixes.**
The candidate passed **136 focused cases**, **2238 caller regressions** and all
**five public-command audits**. Both pytest runs reported the real `~/.co`
unchanged. The merge is still local and uncommitted; the candidate can now proceed
to a Draft PR for contract review, with the #3055 dependency disclosed.

Local extraction date: 2026-11-19. Branch: `codex/rem-source-interface-coordination`.
The author committed and pushed the earlier candidate as `02cf5ff6`. On 2026-11-20,
main `fe50d34632e663ab7f1b6e24f27fd230401acf6a` was merged into the local working
tree without committing or pushing. The current candidate includes conflict
resolutions, compatibility changes and the later approval/acquisition fixes. The
latest results are **136 focused cases and 2238 caller regressions**, plus all
five audits in one audit run. The earlier 103/2104 results below describe the
merged candidate before those review fixes.
The implementation agent has not run tests, `co audit` or live demonstrations,
or made commits, pushes or external comments. Runtime evidence below was supplied
by the user, with pre-merge and merged-candidate results separated below.

Before the merge, the shared suite passed **73 focused cases**, **1269 caller
regressions** (before the help-only correction), and five CLI audits. Those results
do not validate the current merged working tree. The updated commands below include
current-main callers and five public-command audits, with `co rem collect` replacing
the compatibility-only `co rem sync` audit target.

## Base and ownership

The shared-only comparison base is #3055 head
`784d00a5ecddd99dd0a0f0b3cc368d337833dd50`, already an ancestor of this branch.
#3055 was open/unmerged when checked. A PR against upstream main before it merges
will include that foundation too; the PR description must declare the dependency.
Before merge, refresh the base and review the resulting diff once #3055 lands.
A Draft PR may be opened earlier with that dependency disclosed.
The local main merge does not rewrite history or change any other working tree.

The candidate includes generic lifecycle/CLI/Reader wiring, exact version routing,
synthetic contract/integration tests and documentation. It excludes Obsidian CLI
commands, all three real adapters, SDKs, credential implementations, stores and
provider skills. #3064, #3060 and #3223 retain their source-owned migration work.

Source code was inspected at these revisions:

- Obsidian #3064: `01ff73fdeb289a42f113a7bdae2763bf1222d3a7`, plus its local uncommitted candidate.
- Asana #3060: `f1a2e7eddb4bab33e10c12e50d16bc45e56c87c8` — local index/body reads, account/task identity and owner-aware gathering.
- Granola #3223: `544d79d680dc097dce6d0db62b96957f722f237d` — selected snapshot reads, full-record hash references and normalization.

The code comparisons support contract design; they do not certify the unported
real integrations. Granola's generated-summary scope must still exclude transcripts,
private notes, audio and attachments in its own migration tests.

## Tests to run

Activate the existing development environment, enter the coordination worktree,
then verify the branch and select this checkout explicitly:

```bash
test "$(git branch --show-current)" = 'codex/rem-source-interface-coordination' &&
export PYTHONPATH="$PWD"
```

Run the focused contract tests first:

```bash
python -m pytest -q \
  tests/unit/test_rem_source_hooks.py \
  tests/unit/test_rem_source_approval.py \
  tests/unit/test_rem_source_citations.py \
  tests/unit/test_rem_source_integration.py \
  tests/unit/test_rem_source_versions.py
```

The synthetic suite covers inactive-state import isolation, explicit configure,
saved counters, dry-run, fetch publication, stale/blocking failures, strict budgets,
owner/end inputs, rejected-run progress, exact old/new versions, opaque-target
restart, Reader/filter integration and revocation on retained/retried work.
A writer/read interleaving case checks the no-writer-lock offline contract.

Then run the affected existing callers, including main's native-task scheduling,
claim retention, collection, catchup and topic/knowledge paths:

```bash
python -m pytest -q \
  tests/unit/test_rem_files.py \
  tests/unit/test_rem_queue.py \
  tests/unit/test_rem_leads.py \
  tests/unit/test_rem_daily_round.py \
  tests/unit/test_rem_page_review.py \
  tests/unit/test_rem_reader_model.py \
  tests/unit/test_rem_runner.py \
  tests/unit/test_rem_investigate.py \
  tests/unit/test_rem_service.py \
  tests/unit/test_rem_consent.py \
  tests/unit/test_rem_config.py \
  tests/unit/test_rem_first_run.py \
  tests/unit/test_rem_native_round_regressions.py \
  tests/unit/test_rem_next_submit.py \
  tests/unit/test_rem_unstick.py \
  tests/unit/test_rem_collect.py \
  tests/unit/test_rem_catchup.py \
  tests/unit/test_rem_topic_map.py \
  tests/unit/test_rem_abstract_knowledge.py \
  tests/unit/test_rem_decision_authorship.py \
  tests/unit/test_rem_nightly_abstract.py \
  tests/unit/test_rem_carried_claim_context.py \
  tests/unit/test_rem_retained_quote_context.py \
  tests/unit/test_rem_project_pages.py \
  tests/unit/test_rem_instructions.py \
  tests/unit/test_rem_sync_next_names_a_kept_run.py \
  tests/unit/test_rem_exec_schedule.py \
  tests/e2e/cli/test_rem_commands.py \
  tests/e2e/cli/test_rem_help_contract.py
```

Inspect the public command contracts separately:

```bash
co audit co rem sources
co audit co rem sources connect
co audit co rem sources remove
co audit co rem collect
co audit co rem start
```

Main retains `sync` and its direct help page for compatibility, but does not list it
as a command row on the root REM help page. `co audit` walks listed commands from
`co --help`, so `co audit co rem sync` has no reachable page. The merged candidate's
root help is identical to main. Keep that upstream layout; the caller regression
suite still covers sync behavior and its direct help contract.

Static scope check (no provider-name matches expected):

```bash
rg -n 'asana|obsidian|granola' \
  connectonion/rem/{runner,investigate,daily,native,native_round,leads}.py
```

This prerequisite deliberately installs no real provider. Use synthetic tests
here; perform real Obsidian/Asana/Granola demonstrations on their migration branches
once they adopt the contract. Independent runner retrieval remains outside these
hooks' selection boundary.

## Static review record

Static checks on 2026-11-19:

- All 23 Python files in the shared-only inventory parsed with `ast.parse`, without importing/executing project code.
- `git diff --check` reported no whitespace errors.
- The six generic-stage files in the provider-name scan above had no matches.
- Changed Markdown fences and relative links were checked; referenced test paths and the existing virtual-environment activation file exist.
- An independent AI static reviewer rechecked the lock policy, mail-only acquisition, retained-evidence guards, ownership-cache lifetime, effective-scope revalidation and pending-count validation. No further definite P1/P2 issue was identified in the reviewed scope. This is not a runtime pass, a real human review or rendered desktop/mobile UI validation.

Review led to four concrete fixes: offline hooks cannot take the storage writer
lock; mail-only sync does not acquire registered sources; removing a registration
cannot release retained evidence from authorization; routing tables are reused
within one operation while current authorization is always rechecked.

## Current file inventory against main

The current working tree differs from main `fe50d346` in **38 files**, including
the new approval regression file (21 implementation/help, 10 test/fixture, 7 docs).
This includes the five inherited #3055-only files and the shared prerequisite;
`topic_map.py` is an additional compatibility caller introduced by this main merge.
The earlier 31-file list measured the pre-merge shared increment above #3055.
Comparing the merged tree with #3055 now also includes intervening main changes,
so that old comparison is no longer the review inventory.

```text
connectonion/cli/commands/rem_commands.py
connectonion/cli/commands/rem_help.md
connectonion/cli/commands/rem_output.py
connectonion/rem/daily.py
connectonion/rem/extract.py
connectonion/rem/files.py
connectonion/rem/inquiry.py
connectonion/rem/investigate.py
connectonion/rem/leads.py
connectonion/rem/native.py
connectonion/rem/native_round.py
connectonion/rem/page_review.py
connectonion/rem/project_pages.py
connectonion/rem/queue.py
connectonion/rem/reader_model.py
connectonion/rem/runner.py
connectonion/rem/service.py
connectonion/rem/source_citations.py
connectonion/rem/source_hooks.py
connectonion/rem/source_versions.py
connectonion/rem/topic_map.py
docs/blog/2026-11-15-a-batch-is-what-changed.md
docs/blog/2026-11-15-a-next-step-that-pointed-at-nothing.md
docs/blog/2026-11-15-a-source-hook-starts-with-selection.md
docs/rem/source-interface-contract.md
docs/rem/source-interface-coordination.md
docs/rem/source-interface-validation.md
docs/rem/source-interface.md
tests/unit/rem_source_fixtures.py
tests/unit/test_rem_investigate.py
tests/unit/test_rem_leads.py
tests/unit/test_rem_runner.py
tests/unit/test_rem_source_approval.py
tests/unit/test_rem_source_citations.py
tests/unit/test_rem_source_hooks.py
tests/unit/test_rem_source_integration.py
tests/unit/test_rem_source_versions.py
tests/unit/test_rem_sync_next_names_a_kept_run.py
```

The ignored local `IMPLEMENTATION_PLAN.md` and external handoff files remain outside
the PR inventory. Git's index contains the local merge result and resolved entries;
no merge commit or push has been made by the implementation agent.

## User-run evidence and correction history — 2026-11-20

All results below were supplied by the user from the existing GitHub virtual
environment on macOS/Python 3.12. The commands selected the named worktree through
`PYTHONPATH`. They ran against local uncommitted candidates above `1f4fa0de`, not
against that committed HEAD alone. No CI or clean installed-wheel pass is claimed.

| Candidate | Focused checks | Caller regressions | CLI audits |
| --- | --- | --- | --- |
| Shared prerequisite | 73 passed in 4.27s | 1269 passed in 46.63s before the help-only correction | Five commands passed; sources discovers 4 pages, each other command 1 page. |
| Separate three-provider integration | 1337 passed in 14.68s | 1269 passed in 46.26s | The same five commands passed. |

The shared caller regression preceded the help formatting correction and added
navigation test. At that time no shared implementation code changed after the regression run;
shared focused tests and audits were then rerun. The later local main merge changes
implementation code again and requires new results. The integration run used matching
shared content except for its explicit provider registrations. Test counts overlap
between these suites and must not be presented as a count of distinct tests.
Both integration pytest stages reported that the real `~/.co` was unchanged.
No warning summary appeared in the final integration output.

The user-run failures led to three corrections before those passing results:

1. Two callers still referenced removed `page_review.SOURCE_ID`. Queue/lead paths
   now use `source_id_pattern()`; eight focused cases and the existing queue/lead
   suites cover legacy, registered and opaque citations. This expanded the shared
   inventory from 29 to 31 files.
2. Sources help listed children in an inline sentence that the audit walker could
   not discover. Standard subcommand rows and a root-to-child regression now cover
   add/connect/remove; the sources audit discovers all four pages.
3. In the separate integration branch, Obsidian's zero-wait writer lock rejected
   a second collector. Bounded waiting, a forced-contention test and direct Granola
   fixture imports addressed the failed test and late-plugin warning. This did not
   alter the shared prerequisite's implementation.

## Local main integration — 2026-11-20

Main `fe50d346` and the published shared candidate `02cf5ff6` had eight conflicted
files and eighteen conflict blocks. The local resolution retains main's collect
navigation, backlog display, append claim guards, abstraction review, worker
handoff and task-failure behavior alongside shared-source lifecycle checks.

Compatibility changes also cover:

- Exact-version replacement and current-main claim retention together; uncited
  entries may still be cleaned up without restoring unusable evidence.
- Source acquisition under the native preparation watcher/deadline, outside the
  long notebook lock; repeated stalls are checked before another acquisition.
- New catchup nights, explicit discard and the collection-only held path; an
  unfinished task keeps its existing material. Preflight lock waits retain the
  previous worker's identity for main's task handoff rules.
- Revoked retained material becomes a native task fault on submit; notebook I/O
  and invalid ownership data remain round errors rather than being hidden.
- Registered and opaque citations in structured Topics, legacy extraction notes
  and page evidence, preserving main's existing source spellings.

New regression definitions cover these boundaries. AST parsing and whitespace
checks are static checks only: 29 Python files in the 37-file comparison parsed,
the diff against main passed whitespace checks, and the author-run shell script
passed syntax inspection. The staged diff against the older branch HEAD also
reports whitespace already present in incoming main files; those files are
unchanged from main and are outside this PR's comparison. An independent AI
reviewer rechecked the conflict resolutions, task handoff, deadline/stall handling,
topic citation/date parsing and handoff text; no remaining concrete P1/P2 issue
was identified within that static scope. That review does not establish a runtime,
current-main CI or installed-package pass, or rendered desktop/mobile UI coverage.
The later user-run runtime results are recorded separately below.

## User-run merged candidate — 2026-11-20

The user ran the original `all` script with committed HEAD `02cf5ff6` and pending
merge `fe50d346`. The supplied output reports:

- Focused suite: **103 passed in 5.05s**.
- Caller regressions: **2104 passed in 192.75s**.
- Both pytest stages reported the real `~/.co` unchanged.
- `sources` passed on four pages; `sources connect` and `sources remove` each
  passed on one page.
- That first run stopped at `co audit co rem sync`: no reachable help-tree page.
  `collect` and `start` were therefore not executed in that run.

At that stage only the external check script and validation documentation changed
after that run. No implementation or test had changed. The script audits the five public
targets above and offers `audit-remaining` to run only `collect` and `start`.
The compatibility sync audit is not recorded as passing; its old target was
inappropriate for main's current help-tree layout.

The user then ran `audit-remaining` with the same HEAD and pending merge. Both
`co rem collect` and `co rem start` passed on one page each, with all ten rules
passing. The five planned public-command audits are now complete. No `--review`
model audit was run or claimed. The implementation and test files were unchanged
at that point. The review fixes described below subsequently changed that candidate.

## Overall-review corrections — 2026-11-20

Static review identified four uncovered cases: out-of-order acquisition receipts,
effective model routes omitted from approval, configuration changing during
confirmation, and automatic mailbox grants renewing another source's approval.
The implementation now keeps per-source execution approvals, compares stable
confirmation snapshots, and preserves acquisition blocks against overlapping
successes. Legacy registered-source receipts require fresh confirmation.

New synthetic regressions cover each model level, explicit stage routes and their
removal, configuration changes inside confirmation, fresh default lookbacks,
mailbox admission, old receipts and three overlapping acquisition orderings.
Further cases cover reapproving a new model before resuming an old task, cached
extract/inquiry/runner configurations, and successful investigation through a
separate approved render route. Prepared execution snapshots are retained across
retries and task replay; they are not refreshed from a newly approved configuration.
The checks script includes the new source-approval suite and existing consent,
configuration and first-run caller tests. The implementation agent did not run
them; the author supplied the passing results recorded below.

## User-run corrected candidate — 2026-11-20

The author ran `focused`, `regression` and `audit` with committed HEAD `02cf5ff6`
and pending main merge `fe50d346`, after the approval/acquisition fixes.

- Focused: **136 passed in 7.59s**.
- Caller regressions: **2238 passed in 222.08s (0:03:42)**.
- Both pytest runs reported the real `~/.co` unchanged.
- All five public audits passed: sources (4 pages), connect, remove, collect and
  start (1 page each). Every rule passed on every discovered page.
- No `--review` model audit or upstream CI result is claimed.

All 38 files in the recorded handoff matched their saved hashes when these results
were received. Only validation/publication documentation was then updated; code
and tests were unchanged. Counts can overlap and are not a distinct-test total.

## Publication boundaries

The previous GitHub check on 2026-11-20 found #3055 open/unmerged at `784d00a5`.
Its dependency must remain disclosed while its changes are still included here.
The merge with main is currently local and uncommitted, so the remote branch still
contains the earlier candidate. The updated author-run checks have passed.
The remaining publication steps are to stage the review fixes and new approval
test, complete the local merge commit, push the branch and create the Draft PR.
Retain Draft status for contract review. No commit or push was performed by the
implementation agent.

Source revisions inspected remain Asana #3060 `f1a2e7ed`, Granola #3223 `544d79d6`,
and Obsidian #3064 `01ff73fd` plus the preserved local candidate. Their production
adapters, clients and stores are excluded from this shared-only PR. The separate
integration worktree was not updated by this main merge; its earlier passing
results do not establish compatibility with the new merged shared candidate.
Live accounts, existing-installation migration, Windows/Linux and React/O Chat
journeys still need their own evidence.
