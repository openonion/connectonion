# Granola: native REM intake implementation evidence

Date: 2026-11-07 (Australia/Sydney). Implementation candidate: `6a1d98f0d141ab943fc655d23f1808cef64b64ad`.
Documentation-only follow-up commits may sit above this tested product candidate.

## Delivery and common dependency

This source remains on its own complete feature branch; no sibling feature branch
was merged into it. Shared boundary origins are `0617716b` and `a2ba86f3`, ported
onto this source as `5006a4b9` and `46e84008` with source-aware dispatch preserved.
The feature is built on team develop `049a74e8`; refreshed upstream main `9f80e636`
was inspected, not broadly merged. An upstream PR still needs a clean selected
base and its own validation. No release, PR/MR or develop merge was performed.

## Normal flow

Follow [native source setup](../cli/rem-native-sources.md) and
[Granola selection](../cli/granola-native-connection.md). Connect metadata once,
approve sources/model, then normal init and sync collect remotely before existing
REM processing. Existing scheduled dispatch calls the same sync function. Reader
opening does not collect. Standalone source commands remain diagnostics/recovery.

Automatic collection is a new user-requested extension of the historically
client-approved manual MVP; it is not recorded as new client approval. Select a
personal folder or child ID. include_children: true explicitly grants current and
future personal descendants. Every selected folder must have explicit space_id:
null; shared/unknown descendants fail before note bodies. Canonical records retain
the actual child folder plus the approved root/path. Bounded limit coverage is not
whole-folder completeness. The saved key is bound by hash; profile is a local
label, not verified remote account identity. Changed keys/scopes require separate
outputs or a reviewed reconnection. Summaries and allowed metadata only reach
records/models. Detail requests do not request transcript; vendor responses may
still contain extra fields, filtered at the client DTO boundary before collection.
The API has no claimed response-field mask.

## Offline evidence

At the implementation candidate, the source selection below reported **327 passed, 1 skipped**:

```bash
python -m pytest tests/unit/test_*granola*.py \
  tests/unit/test_rem_remote_sources.py tests/unit/test_rem_remote_prompt.py \
  tests/unit/test_env_secret_prompt.py tests/unit/test_init_rem.py -q
```

The skips concern sibling provider features absent on the isolated source branch.
Synthetic cases cover configuration without body reads, consent/scope changes,
first/repeat/changed/repeat, old immutable citations, failed model retry, partial
or denied reads, and existing scheduled due-slot dispatch. New identities/scopes,
locks and private-field boundaries are checked where applicable. Tests inject
model callbacks; they do not constitute new model-quality acceptance. Original
source Skills and client stage/page Skills/taxonomy remain unchanged; only prompt
composition reuses original-provider rules and excludes them from derived inputs.

A separate **test-only** composition of all three candidates reported **1,443
passed / 1 failed** across source and shared REM/runner/investigation/Reader-link
checks. It is local and was not merged into any deliverable branch. The failure,
`test_first_batch_runs_before_the_clock_is_installed`, was freshly reproduced on
clean develop `049a74e81c0f347dddf1d2c1378d970d950e481e` with the same assertion
(expected batch then install, observed install). The test and scheduler were not
changed. This is a known baseline failure, not an all-green repository result.

The final test-only combined CLI ran `co audit co --json`: **396 pages**, all ten
rules **396/396**, no findings. `co rem sources connect` was reached. This is a
rule/terminal-vs-pipe audit, without a model review, not browser or human acceptance.
An intermediate combined-help editing error was caught, restored and the full
audit rerun on the corrected pages; only the corrected run is counted here.

Independent AI code/usability reviews inspected source selection, consent,
credential restoration, locks, new identities, child scope, metadata failures and
help discovery. Significant findings were fixed and targeted checks repeated.
This is an AI review of named code/CLI states, not a human-founder or browser pass.

## Live acceptance still pending

The user explicitly chose to finish code first and defer real-account acceptance.
No new successful live-account import/change/model-to-Reader run, actual OS/Codex
timer trigger, browser original-link click or desktop/mobile visual acceptance is
claimed. Existing historical demonstrations do not validate this candidate.
Jira/Granola encrypted synthetic credentials were read by fresh subprocesses
without inherited provider keys; Microsoft refresh lifecycle used offline mocks.
These do not replace real background authorization. Scheduled tests simulate the
existing due slot; no timer was installed or fired. Later use only the previously
approved dedicated test scopes, and let the account holder make source edits.

Official API references: [personal API access](https://docs.granola.ai/help-center/sharing/integrations/granola-api),
[folder hierarchy](https://docs.granola.ai/api-reference/list-folders),
[list notes, including descendants](https://docs.granola.ai/api-reference/list-notes),
[note detail fields](https://docs.granola.ai/api-reference/get-note).


## Interactive onboarding follow-up

The native terminal connection no longer requires a scope file. Run
`co rem sources connect` to choose an installed application, or append `granola`.
Global interactive init calls the same selector. Missing saved credentials use
existing Microsoft auth or hidden encrypted key entry. Numbered metadata choices
are explicit; q cancels, empty/ambiguous lists fail closed, and source/model
approval remains a later step. Scripts retain NAME + --config FILE; nonterminal
wizard attempts stop before credential access or network. Explicit credential
file/home choices are preserved while listing and revalidating the scope.

This update's source/shared selection: 340 passed, with expected sibling-feature
skips. After the final credential-location fix, the 12 common wizard cases passed
again on each branch. These overlapping runs are not added together. Scoped help
checks use the existing co audit engine: source commands + sources + init, with
no findings (Jira11/OneNote16/Granola10 pages). The earlier396-page combined audit
and1443-pass combined regression above precede this follow-up and are historical.
Independent AI review found malformed metadata and encrypted-store error edges;
these were fixed with regression cases. No live credentials, source edits, model,
actual timer or browser acceptance was performed; those remain user-deferred.


## Declined initialization approval

The Jira terminal trial declined source approval, yet the previous shared init
continued metadata mapping and offered a32-page owner/Skills model estimate.
The user had not approved that model gate. Shared fix240bd874 now exits1 after
source refusal, before source clients, collection, map, estimate or model work;
no schedule installation follows. Ordinary and estimate-only refusal cases fail
if those boundaries are crossed. Init plus this source's native tests:53passed.
Independent AI rechecked8overlapping consent/estimate cases. This does not change
the customer's default owner/Skills investigation or prove live source/model
acceptance. Existing map stubs are preserved; no real notebook data were deleted.


## Imported projects and owner mapping

Jira live collection completed (six canonical records, one daily file and one
checkpoint); initialization then failed in owner mapping because imported project
rows have no coding-session count. Shared owner-summary fix filters for positive
session evidence without changing the project report or imported identity rows.
It neither invents session totals nor attributes imported work to the owner.
Map/import/native/init selection:136passed on this source. Jira additionally
passed a full synthetic owner+Jira map-only CLI init with models/scheduling forbidden.
Independent AI reviewed five overlapping cases. The user stopped personal live
trials due to exhausted token allowance and handed further acceptance to teammates.
Do not infer Jira API-token expiry or successful live model/Reader completion.
