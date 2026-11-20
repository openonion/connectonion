# Shared source prerequisite: scope and validation

**Current status: the author confirmed that the test rerun passed; the latest
model help reviews still report five findings.** The confirmation did not include
fresh test counts or timings, so the earlier detailed results below remain
historical. The pasted review output shows all ten ordinary rules passing on
four sources pages and on the collect and start pages.

The remaining model findings are three `short_reference` findings on
sources/add/remove, one `simple` finding on collect's batch-limit wording and
one `simple` finding on start's full-access wording. Connect has no findings.
These are recorded as unresolved, not waived or passed. The author limited this
round to shared-interface or Obsidian defects; no WhatsApp/list-number feature or
additional general-help rewrite was made in response to those findings.

Static comparison with main `fe50d346` confirms that WhatsApp's chat-ID selection
predates this PR. Registered-source project removal is part of this PR, but its
contract forwards the project ID to the adapter; shared row-number resolution is
not part of the implemented contract. The reported findings do not establish a
Source lifecycle or Obsidian adapter failure, nor does this classification prove
that all runtime behavior is correct.

Draft PR #3228 was checked on 2026-11-20: open, targeting main, on branch
`codex/rem-source-interface-coordination` at `dc64f1c2`. Local help,
help-contract and validation changes have not been committed or pushed. The
latest bookkeeping update changes documentation only. No product execution,
test run, commit or push was performed by the implementation agent.

Local extraction date: 2026-11-19. Branch: `codex/rem-source-interface-coordination`.
The author committed and pushed the earlier candidate as `02cf5ff6`. On 2026-11-20,
main `fe50d34632e663ab7f1b6e24f27fd230401acf6a` and the conflict, compatibility,
approval and acquisition fixes were initially prepared locally, then committed
and pushed by the author as `dc64f1c2`. Only the subsequent help, help-contract
and validation documentation updates remain uncommitted.
The earlier detailed implementation results were **136 focused cases and 2238
caller regressions**, plus all five audits in one audit run. The earlier 103/2104
results below describe the merged candidate before those review fixes.
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

The current working tree differs from main `fe50d346` in **40 files**, including
the approval regression file and revised help-contract assertions
(21 implementation/help, 12 test/fixture, 7 docs).
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
tests/e2e/cli/test_rem_commands.py
tests/e2e/cli/test_rem_help_contract.py
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

## Model help-review follow-up — 2026-11-20

The author ran `co audit co rem sources --review --model co/gemini-4-hydrogen`.
All ten ordinary rules passed on all four pages. The model flagged `simple` on
sources, add, connect and remove, and `short_reference` on sources, add and remove.
The command returned a failure verdict, so the chained collect/start model reviews
did not run. This was a completed review with findings, not a missing model verdict.

The four help pages now describe settings, content reads, connection checks and
approval in plain words. Source names such as gmail already work as references;
the shared CLI does not resolve list numbers for chat/project options. The help
states this limitation without claiming the requested feature exists. Numbered
chat/project selection remains a usability follow-up.

The author then repeated the sources review with the same model. All ten ordinary
rules again passed on all four pages. No `simple` findings remained; connect had
no findings. Sources, add and remove each retained a `short_reference` finding,
so the source-group model review still returned a failure verdict with three
findings. These all concern actual list-number selection capability. Rewriting
help to claim that capability without implementing it would be inaccurate.
No new help-test or collect/start review result was supplied with this output.

The author subsequently supplied the collect model review: all ten ordinary rules
passed on one page, with one `simple` finding about the batch-reader sentence.
The sentence now says that the command extracts information from one batch of new
material and updates notebook pages. Other collect behavior and help constraints
are unchanged. The author then reran the collect model review: all ten ordinary rules again
passed, but the model flagged the archive-continuation sentence as too technical.
The collect page has now been simplified as a whole, preserving approved-source
and single-batch limits, the five-minute archive continuation budget, and the fact
that `--source` does not restrict the additional session/archive reads. An
independent AI static reviewer found the revised wording consistent with the code.
The latest collect wording awaits author verification; help-test and start-review
results have not been supplied.


The author then supplied the start model review: all ten ordinary rules passed,
with one `simple` finding on the desktop-automation skip sentence. The revised
text specifies a scheduled CLI run and this notebook's Codex desktop automation
starting within ten minutes. It does not claim that opening the desktop app or
completing arbitrary work triggers the skip. Independent AI static review checked
that wording against the notebook-specific automation run index and scheduler.
No revised start model verdict or final help-test result has been supplied.

The author's third collect model review passed all ten ordinary rules on one
page but returned one `simple` finding on the list of later processing steps.
The sentence now says that collect does not run further research, draw lessons
across pages or translate pages. Extraction and page updates remain explicit;
the model's broader suggestion that collect does no summaries was not adopted.
This is a wording-only correction, not a new functional failure. An independent
AI static review found the replacement consistent with the collect-only path
and separate research, abstraction and translation steps. This was not runtime
or rendered UI validation. The sentence still awaits author verification;
no model-review pass is claimed.

The author's fourth collect model review again passed all ten ordinary rules
but returned one `simple` finding on the sentence explaining `--source`.
The page now uses short paragraphs for batch limits, additional reads, source
selection and output. It explicitly says that `--source` limits source refreshes
and the main batch, not the extra session or archive reads. The waiting count is clarified as
listed mail only, excluding all coding sessions. Two existing help-contract
assertions were updated, retaining both boundary checks rather than dropping
them to accommodate the new text. Independent AI static review also found that
the batch-size limit does not bound pre-batch integration refreshes. The help now
explains that refreshes can read more, and the help contract protects that warning.
The independent AI reviewer rechecked the corrected page and its three boundary
assertions and found no further concrete issue in that static scope. This was
not a runtime, model or rendered-page pass. No runtime behavior or audit rules changed.

The author subsequently confirmed that both commands in the collect handoff
passed: the targeted source-reachability/help-contract pytest invocation and the
collect model review. This was a verbal result confirmation without detailed
pytest counts, timing or full audit output; none have been inferred.

The next start model review passed all ten ordinary rules on one page, but
returned one finding covering `clear` and `simple` on its opening. The full start
page now begins with automatic notebook updates and distinguishes terminal use
from scripts, new/changed approval from reused approval, and the initial batch
before schedule installation from later starts. Existing approval from init
also suppresses the initial batch. Obsolete six-slot defaults and retired
translation/draft caps have been removed in favor of the saved configuration.
The old guarantee of no shell/network access and writes only under .state/tasks
was incorrect: permissions depend on runner/task, scheduled Codex CLI uses the
network, and research/delegated tasks may use full access. The revised help says
so. Independent AI static review rechecked the corrected start page and found
no further concrete wording issue. This was source-text review, not runtime or
rendered-page validation. These are documentation corrections, not permission
or runtime changes.

The author's latest start model review passed all ten ordinary rules on one page
and returned only a `simple` finding on the ten-minute desktop-update sentence;
`clear` was no longer flagged. The sentence now says that an update already
started by the Codex desktop app for this notebook causes the scheduled
command-line run to be skipped within ten minutes. This still means an update
started, not that the app merely opened or the update completed. An independent
AI static recheck confirmed those semantics without executing the product.
This wording has not yet received an author-run model verdict; no start review
pass is claimed.

Runtime implementation is unchanged since the 136/2238 pass. Only start help
changed after the author's collect pass. Recheck the help-contract file and start
audit/model review; the unchanged collect review need not be repeated. Sources
still has its recorded short-reference capability gap. No model run or runtime
test was executed by the implementation agent in this correction round.

## Full-rerun help assertion correction — 2026-11-20

The author ran `run-shared-checks.sh all` on
`codex/rem-source-interface-coordination`, committed HEAD `dc64f1c2`, with the
local help corrections. Focused tests: **136 passed in 5.96s**. Caller regression:
**1 failed, 2237 passed in 216.58s (0:03:36)**. Both stages reported the real
`~/.co` unchanged. Because the script stops at a failure, ordinary audits did
not run. The author separately confirmed the three model reviews were not run.

The sole failure was
`test_start_help_names_the_confinement_and_the_undo`, which asserted two fixed
permission flags in printed help. The implementation already uses different
permissions by runner/task. The corrected test,
`test_start_help_explains_runner_access_and_the_undo`, checks the scoped Access
section for commands/files/network, runner/task-dependent permissions, scheduled
Codex network access and possible full access. It rejects the obsolete absolute
restrictions and checks the explicit `Undo: co rem stop` line. It also requires
a successful help exit. No test is skipped or disabled.

Independent AI static review confirmed that the old assertion did not exercise
runtime isolation and that the replacement retains meaningful access/undo
coverage. Only this test and validation/publication records changed in the
correction; no runtime, help or audit rule changed. No test or product command
was executed by the implementation agent. The author subsequently confirmed the
test rerun passed, without fresh counts or timings. The latest model-review
findings are recorded in the current-status section above.

## Publication boundaries

The previous GitHub check on 2026-11-20 found #3055 open/unmerged at `784d00a5`.
Its dependency must remain disclosed while its changes are still included here.
The author committed the main merge and approval/acquisition corrections as
`dc64f1c2`. This subsequent help-only correction remains local and uncommitted.
The author confirmed the test rerun passed; five model-review findings remain.
Draft PR #3228 already exists on this branch at `dc64f1c2`. Commit the local
help/documentation and help-contract changes and push the same branch to update
that Draft, retaining the unresolved review findings in its validation record.
Creating another PR is unnecessary.
Retain Draft status for contract review. No commit or push was performed by the
implementation agent.

Source revisions inspected remain Asana #3060 `f1a2e7ed`, Granola #3223 `544d79d6`,
and Obsidian #3064 `01ff73fd` plus the preserved local candidate. Their production
adapters, clients and stores are excluded from this shared-only PR. The separate
integration worktree was not updated by this main merge; its earlier passing
results do not establish compatibility with the new merged shared candidate.
Live accounts, existing-installation migration, Windows/Linux and React/O Chat
journeys still need their own evidence.
