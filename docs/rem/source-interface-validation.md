# Shared source prerequisite: scope and validation

Local extraction date: 2026-11-19. Branch: `codex/rem-source-interface-coordination`.
Committed HEAD remains `1f4fa0de`; the implementation described here is uncommitted.
The implementation agent has not run tests, `co audit` or live demonstrations,
or made commits, pushes or external comments. Runtime evidence below was supplied
by the user.

Latest shared user-run results: **73 focused cases passed** after the help correction,
and all five requested audits passed. The sources audit now discovers four pages;
connect, remove, sync and start each pass for one page. The earlier **1269 caller
regressions passed** before the help-only correction. No shared implementation code
changed after that regression run. Historical failures and follow-ups appear below.

## Base and ownership

The shared-only comparison base is #3055 head
`784d00a5ecddd99dd0a0f0b3cc368d337833dd50`, already an ancestor of this branch.
#3055 was open/unmerged when checked. A PR against upstream main before it merges
will include that foundation too; the PR description must declare the dependency.
Before merge, refresh the base and review the resulting diff once #3055 lands.
A Draft PR may be opened earlier with that dependency disclosed.
This extraction did not rewrite history or change any other working tree.

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
  tests/unit/test_rem_source_citations.py \
  tests/unit/test_rem_source_integration.py \
  tests/unit/test_rem_source_versions.py
```

The synthetic suite covers inactive-state import isolation, explicit configure,
saved counters, dry-run, fetch publication, stale/blocking failures, strict budgets,
owner/end inputs, rejected-run progress, exact old/new versions, opaque-target
restart, Reader/filter integration and revocation on retained/retried work.
A writer/read interleaving case checks the no-writer-lock offline contract.

Then run the affected existing callers:

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
  tests/unit/test_rem_native_round_regressions.py \
  tests/e2e/cli/test_rem_commands.py \
  tests/e2e/cli/test_rem_help_contract.py
```

Inspect the public command contracts separately:

```bash
co audit co rem sources
co audit co rem sources connect
co audit co rem sources remove
co audit co rem sync
co audit co rem start
```

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

## Final shared-only file inventory

31 files relative to #3055, including seven currently untracked new files. The
working tree has 23 tracked modifications and seven untracked files relative to
its committed prototype. `source_versions.py` is already changed in that prototype,
so it belongs to the 31-file PR scope even though it is not a new working-tree edit.
The existing `test_rem_source_versions.py` is unchanged but must be run.

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
docs/blog/2026-11-15-a-source-hook-starts-with-selection.md
docs/rem/source-interface-contract.md
docs/rem/source-interface-coordination.md
docs/rem/source-interface-validation.md
docs/rem/source-interface.md
tests/unit/rem_source_fixtures.py
tests/unit/test_rem_investigate.py
tests/unit/test_rem_runner.py
tests/unit/test_rem_source_citations.py
tests/unit/test_rem_source_hooks.py
tests/unit/test_rem_source_integration.py
```

The ignored local `IMPLEMENTATION_PLAN.md` and the external PR-description draft
are preparation artifacts, not part of this inventory. Staging/committing remains
for a later user-authorized step; no index changes were made here.

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
navigation test. No shared implementation code changed after that regression run;
shared focused tests and audits were then rerun. The integration run used matching
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

## Publication boundaries

GitHub was rechecked on 2026-11-20. #3055 remains open/unmerged at the same
`784d00a5` reference. Main is now `fe50d34632e663ab7f1b6e24f27fd230401acf6a`;
this candidate has not been rebased or validated against that newer main.
The 31-file inventory is the increment above #3055, not a promise about a PR
comparison against main before the dependency merges.

Source revisions remain Asana #3060 `f1a2e7ed`, Granola #3223 `544d79d6`, and
Obsidian #3064 `01ff73fd` plus the preserved local candidate. Their production
adapters, clients and stores are excluded from this shared-only PR. The separate
local integration branch is supporting offline evidence, not a replacement for
source-owned migration PRs or proof that their remote branches have been updated.

Before publishing, review the actual committed diff, declare the #3055 dependency,
and retain Draft status while the concrete contract is reviewed. If the base or
code changes, reassess affected checks. Live accounts, existing installation
migration, Windows/Linux and React/O Chat journeys were not verified by these runs.
