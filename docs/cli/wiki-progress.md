# Wiki progress and remaining work

Reviewed 2026-09-17 against `feat/wiki-1443-followups`, commit `85315404`,
and live [draft PR #1454](https://github.com/openonion/connectonion/pull/1454).
The PR targets **1.8.7**, with no confirmed release date. The implementation
is a local, single-owner Markdown notebook.

## Available functionality

| Capability | Entry point | Evidence / limitation |
|---|---|---|
| Initial source discovery and ranked People/Project/Skills map | `co wiki init` | Installed-skill skeletons are created before the model stage. People/project ranking remains a Skill workflow; init now hands off to a separate investigation stage; full live-account initialization still needs acceptance. |
| Deterministic discovery and page skeletons | `map-skills`, `scan people`, `scan projects`, `stub person`, `stub project` | `map-skills` creates source-linked installed-skill pages without executing or copying runtime skills; reruns preserve page prose. Explicit skill roots are supported. |
| Existing-person investigation | `people`, `investigate people/alice.md` | Collects mail/session evidence, digests large inputs, updates the existing page; earlier live owner run is recorded in acceptance evidence. |
| Incremental updates and corrections | `subscribe`, `sync`, `unsubscribe` | Checkpoints, no-op handling, failure accounting and writer locking exist. |
| Derived decisions and principles | `abstract` | Command and Skill exist; whole lifecycle acceptance remains incomplete. |
| Background updates | `start`, `stop` | macOS launchd runs scheduled sync. Does not yet alternate sync with unfinished investigations. |
| Reading and diagnostics | `list`, `show`, `search`, `open`, `status`, `logs`, `usage`, `doctor` | HTML is a generated snapshot; reopen to refresh. No hosted login/admin UI. |
| Shared model execution | All model stages use `co ai` | Codex, Claude Code and COAI adapters exist. Claude subscription path lacks live acceptance. |
| Attachments | Investigation collection | PDF, DOCX, XLSX, PPTX, ICS, HTML and text readers exist; errors are reported. |

Full syntax, configuration and source boundaries: [CLI contract](wiki.md).

## Progress and performance evidence

On 2026-09-17, 242 focused Wiki, CLI, shared-harness and default-Skill tests
passed in 3.46 seconds locally. These use fixtures; their runtime measures
the test suite, not real Wiki generation speed.

The September 15 acceptance record contains a real synthetic Luna run:
extraction used 80,897 input / 1,576 output tokens; maintenance used 204,541
input / 3,660 output tokens. Cached input was 50,688 and 150,016 respectively
and is already included in input. A separate small Gemini extraction reported
$0.04813312. These are individual observations, not per-user pricing or a
full-mailbox estimate. Maintenance cost is still material even with small
source inputs. See [dated acceptance evidence](../testing/wiki-acceptance.md).

Live GitHub checks at the reviewed commit are not green: Python 3.10–3.13
test jobs, the blog gate and release metadata gate report failures. The
inspected Python 3.10 job reports 10,354 passed, 23 skipped and two failures:
`test_ai_forwards_full_access_options` and
`test_ai_forwards_json_and_resume_options`. Both expected calls omit the new
`timeout=600` argument. Both failures reproduce locally; this review updates
those expectations without changing runtime behavior. Other Python jobs must
be rechecked after the fix; their causes are not inferred from the 3.10 log.

The blog gate asks for a clearer narrative about the hidden token cost, rather
than a verification checklist. The metadata gate requires explicit
`Proposed target version` and `Estimated release window` fields in the PR body.
These remain release follow-ups; local changes do not make remote CI green.

## Remaining product work

The two largest automation gaps are budget enforcement and scheduling the
unfinished investigation queue. Source completeness and release acceptance
are additional work, so this is not a claim that only two tasks remain.

| Priority | Work | Completion criteria |
|---|---|---|
| P0 | Enforce real provider budgets across init, investigate, extract, maintain and abstract | Shared meter/reservation before work; known and unknown usage distinguished; stop/resume behavior verified. Current attempt/input limits do not enforce 2% initial, 1% daily or $1 spending limits. |
| P0 | Alternate incremental maintenance and unfinished investigations | Persist per-notebook progress, prevent concurrent writers, preserve retryable work on failure, and respect the shared budget. |
| P1 | Complete source listing | Paginate beyond 200 messages per weekly investigation window and own-mail sent history; prove no loss with a busy-window fixture. |
| P1 | Connect Jira discovery/auth | Explicit source selection, successful authorized retrieval, visible partial/failure state. |
| P1 | End-to-end initialization and daily lifecycle | Verify one authorized account through init, update, correction, scheduled continuation and stop; record elapsed time, usage and coverage. |
| Release | Repair remaining gates and refresh acceptance | CI at the resulting commit, live Claude evidence if advertised, cost narrative, release metadata. |
