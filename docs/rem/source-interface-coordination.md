# Shared REM source interface coordination

Updated 2026-11-20 after the Asana and Granola replies in
[#3040](https://github.com/openonion/connectonion/issues/3040).
The three teams support one shared prerequisite PR followed by source-owned
migrations. This record tracks that agreement, the concrete draft choices and
the work needed to prepare the shared PR.

Read the [contract draft](source-interface-contract.md) for signatures,
selection/approval, acquisition, budgets, citations and compatibility cases.
The [implementation overview](source-interface.md) describes the extracted shared
candidate. [Validation and PR scope](source-interface-validation.md) records what
was checked, user-run results and reproducible commands.

## Agreement recorded in the discussion

| Topic | Evidence and current status |
| --- | --- |
| One shared registry/hooks PR, then each team migrates its source | Proposed by Obsidian and explicitly supported by Asana and Granola. Both teams say they have not started a separate shared layer. |
| Acquisition before the long-lived notebook lock | Both teams accept the five proposed interface topics. Adapter storage locking and commit-time approval checks remain concrete design work. |
| Explicit failure policy, budgets and gather context | Both teams accept these requirements. Exact result shapes, clipping policy and argument defaults remain draft choices. |
| Metadata without decrypting credentials or calling services | Explicit Asana requirement. Granola also excludes note reads. |
| Dry-run counts saved local material only | Explicit requirement from both teams. |
| Source import and investigation isolation | Asana excludes unselected sources. Granola also excludes disabled and awaiting-consent sources. |
| Version identity and exact saved citations | Asana retains its source-qualified byte locators. Granola proposes separating its stable record identity from the Reader target. |
| Source-owned compatibility evidence | Granola offered tests for state isolation, local collection, exact citations and scope. Each migration contributes its own coverage. |

Source comments were rechecked on 2026-11-20. [Granola’s new reply](https://github.com/openonion/connectonion/issues/3040#issuecomment-7031298970) replaces #2881 with #3223 and retains its earlier hook/citation requirements. Its authors will port their sources after the shared prerequisite lands. [Obsidian proposal](https://github.com/openonion/connectonion/issues/3040#issuecomment-6968711788),
[Asana response](https://github.com/openonion/connectonion/issues/3040#issuecomment-6969276459),
[Granola response](https://github.com/openonion/connectonion/issues/3040#issuecomment-6976313187).

Granola supplied a regression-form citation example. Its code already implements
stable record IDs, content hashes and exact saved-reference resolution. The
remaining work is to express those existing semantics in the common routing
contract. No further example is required to begin a concrete draft.

## Local branches and reference revisions

The local prerequisite implementation is on `codex/rem-source-interface-coordination` in
`connectonion-rem-source-coordination`, based on prototype `1f4fa0de`.
It contains the #3055 commits as ancestors. The working-tree changes now wire the
shared boundary into the public lifecycle, with no production provider registered.
Review the shared-only diff against `784d00a5`; a PR against main before #3055 lands
will also include that prerequisite. No history has been rewritten, committed or pushed.

The separate `codex/obsidian-rem-single-vault` worktree contains the local
uncommitted three-provider compatibility candidate. Its committed HEAD remains
`01ff73fd`. That candidate is implementation material for extraction and review.
The contract draft records where it needs adjustment after the latest replies.

| Reference | Inspected revision | Role |
| --- | --- | --- |
| [Obsidian #3064](https://github.com/openonion/connectonion/pull/3064) | `01ff73fdeb289a42f113a7bdae2763bf1222d3a7` | Published single-vault integration and starting hooks. |
| [Asana #3060](https://github.com/openonion/connectonion/pull/3060) | `f1a2e7eddb4bab33e10c12e50d16bc45e56c87c8` | Account-bound task snapshots and owner-aware gathering. |
| [Granola #3223](https://github.com/openonion/connectonion/pull/3223) | `544d79d680dc097dce6d0db62b96957f722f237d` | Snapshot hashes, exact references, remote scope and formatting normalization. Current head rechecked on 2026-11-20. |
| [Saved-version foundation #3055](https://github.com/openonion/connectonion/pull/3055) | `784d00a5ecddd99dd0a0f0b3cc368d337833dd50` | Saved-version helpers and existing generic fixes. Still open and unmerged when checked on 2026-11-20. |

The #3064 branch contains adapted #3055 code without its commits as ancestors.
The coordination prototype contains those commits. Reconcile this history when
choosing the shared PR base. Preserve the no-change sync guidance and
project/agenda lead fixes from #3055 with their original provenance.

## Compatibility map

| Surface | Obsidian | Asana | Granola | Shared draft |
| --- | --- | --- | --- | --- |
| Configuration | Local vault and folders | Account and project IDs | Local profile and personal folder or note | Source-owned validation, saved scope and approval invalidation. |
| Metadata | Saved vault/folder names | Saved account/project names | Saved profile/folder/note selection | Generic pre-approval summary, no source bodies or credential/network activity. |
| Acquisition | Scan selected Markdown into snapshots | API tasks/comments into retained snapshots | Generated summaries within approved personal folder/note selection, excluding transcripts, private notes, audio and attachments | Outside notebook lock, source-owned store transaction and commit guard. |
| Offline collection | Saved change stream | Saved task versions | Saved JSONL snapshots | Existing Batch, strict material limits and caller-owned progress commit. |
| Investigation | Saved note handles and paths | Saved tasks and supported owner matching | Saved summary mentions and prior references | Aware start/end, owner request, shared budget and honest coverage. |
| Record identity | Vault instance and note | Account and task | Profile/account and note | Stable identity, namespaced by kind and source instance. |
| Citation target | Version-qualified Obsidian ID | Existing file/offset-qualified Asana ID | Existing adapter path plus record ID and content hash | Preserve target bytes and route by explicit ownership. |
| Time options | Reject unsupported remote-window options | Source validates applicable selection options | Reject since/only/force | Delegate option validation to configure. |

## Draft choices to review while implementing

The requirements above are supported by the replies. The following choices make
those requirements concrete and can be reviewed on the shared Draft PR.

| Decision | Proposed implementation | Review point |
| --- | --- | --- |
| D1. Metadata before consent | Implemented generic rendering from saved selection for all approval states, with no passive adapter import. Explicit add/connect imports the requested configuration implementation. | Confirm the explicit-configuration exception and completeness of the saved consent description. |
| D2. Granola citation routing | Implemented complete-target ownership in source-citations.json. Retain unique source-qualified routing and legacy #3055 callbacks for unmanaged targets. | Agree the metadata format, transaction boundary and handling of existing pages lacking entries. |
| D3. Formatting normalization | Shared Markdown normalization before unresolved filtering, preserving every target byte. | Test the supplied inline example and ordinary source definitions. |
| D4. Budget policy | Strict serialized-character limits, explicit first-item clipping, defer later oversized items, fail when metadata cannot fit. | Confirm truncation and checkpoint semantics with all adapters. |
| D5. Stale material after acquisition failure | Expected temporary errors may use validated saved material. Account/scope/integrity failures block that source. | Confirm each adapter's error classification and partial-refresh publication policy. |
| D6. Gather inputs | start/end, record, handles, owner flag and shared remaining budget. | Agree signature defaults, timestamp meaning and unsupported owner-evidence responses. |

The shared runner's independent Codex/web retrieval remains an execution-policy
question. Hook approval governs the data passed through this contract. The
existing #3064 demonstration must retain its actual multi-source retrieval
qualification.

## Extraction decisions implemented locally

The original #3064 candidate is unchanged. The public interface worktree now has:

1. Shared saved-metadata display, with no passive imports before consent or when
   disabled. Explicit configure returns a selection and the shared writer saves it.
2. Persisted target ownership for opaque Reader references, current-approval gates,
   no fallback for unknown `adapter:` ownership, and same-record matching by kind.
3. Generic Sources normalization before filtering, preserving target/hash bytes,
   including the supplied Granola inline spelling. Reader and archival validation
   use exact source resolution.
4. Strict limits, scope-bound failure receipts, explicit stale-use reporting,
   owner/end gather context and acquisition publication guards.
5. Generic public callers plus synthetic contract/integration fixtures. No source
   clients, credentials, stores or source skills were copied into this prerequisite.
6. Static-review fixes for mail-only acquisition, retained evidence whose adapter
   registration disappeared, and per-operation routing-table reuse. Authorization
   remains freshly checked even within a cached ownership lookup scope.

Offline hooks must read atomic committed state without taking a writer lock while
holding the notebook lock. This concrete contract constraint is now documented and
represented by a threaded synthetic test in the passing user-run shared suite. Asana's inspected
index/committed-byte-range readers do not acquire its writer lock; Granola's inspected
snapshot reader is also lock-free. Actual port concurrency remains each team's proof.

The preserved #3064 candidate has provisional `granola:docs/...` references.
The separate November 20 integration branch now uses selection-returning configure,
canonical `adapter:` targets and a read-only compatibility alias. Its synthetic
migration tests are included in the passing user-run offline suite; source owners
still own production validation.

## Shared prerequisite PR scope

The extracted shared-only range is based on #3055. Review the current working tree
with `git diff 784d00a5` and include the new untracked files listed in the validation note.

| Group | Candidate files | Treatment |
| --- | --- | --- |
| Contract and dispatch | rem/source_hooks.py | Registry, generic configuration dispatch, approval gates, lifecycle and budgets. Real provider registrations accompany their migrations. |
| Version foundation | rem/source_versions.py and its tests | Reuse #3055 helpers and add notebook-aware ownership routing while preserving existing callers. |
| Transactions and retained evidence | rem/files.py and generic hunks in service.py, runner.py, native.py, native_round.py, daily.py, inquiry.py, extract.py | Check scope/approval at each data boundary and use existing recoverable publication. |
| Investigation and citations | Generic hunks in investigate.py, page_review.py, reader_model.py, project_pages.py | Gather context, formatting normalization, persisted routing and exact citation resolution. |
| CLI orchestration | cli/commands/rem_commands.py, rem_output.py, rem_help.md | Route explicit configuration and display saved metadata. Provider-specific option semantics stay with adapters. |
| Evidence and documentation | test_rem_source_hooks.py, test_rem_source_versions.py, relevant integration tests, contract docs and Design Journal | Synthetic shared-contract fixtures plus integration coverage. Record actual results for the extracted revision. |

Code paths in this table are under `connectonion/`. Test paths are under
`tests/unit/` unless an integration test resides elsewhere. Import clients,
provider stores, credentials, source skills and provider-specific tests belong
with their respective migrations. Shared code can define failure types and
store/approval guards while credential access remains source-owned.

## PR ownership and order

| PR | Work to prepare | Owner / dependency |
| --- | --- | --- |
| New shared prerequisite | Registry, protocol, generic callers, version routing, synthetic contract tests, documentation | Proposed coordination by Qi / Obsidian. Both other teams support this split and say they have not started a competing layer. |
| #3064 | Obsidian adapter and single-vault tests against the shared prerequisite | Obsidian team. Remove shared changes from its final standalone diff once the base contains them. |
| #3060 | Asana adapter migration and its compatibility evidence | Asana team, after the shared interface is agreed and landed. |
| #3223 | Granola adapter migration, preserved citation targets and compatibility evidence | Granola team, after the shared interface is agreed and landed. |
| #3055 | Saved-version and generic-fix foundation | Coordinate the shared base with its merge state and preserve attribution. |
| #3039 and #3065 | Existing read-only CLI and create/append work | Their feature scope has no shared-interface implementation dependency. |
| Future multi-vault Obsidian REM | Extend the Obsidian source after the single-vault/shared contract is stable | Separate future feature scope. |

Suggested shared PR title for review preparation:

`refactor(rem): add shared source hooks for selected-source integrations`

The local implementation is prepared on the existing local coordination branch. Once its
contract and tests are reviewable, link it in #3040 so each team can implement
against the same revision. Source teams keep their migration PRs Draft until
migration and compatibility evidence are complete.

## Completion and evidence

The user ran the prepared checks: the shared candidate passed 73 focused cases,
1269 caller regressions and five CLI audits. A separate local adapter candidate
passed 1337 focused cases, 1269 caller regressions and the same five audits.
These are user-supplied offline results, not live-service or cross-platform evidence.
The implementation agent did not execute tests/audits or make commits, pushes or
external comments. See the [validation record](source-interface-validation.md) for
revision limits, static review scope and remaining source-owned work.

The complete contract remains a concrete review candidate. The three teams agreed
the shared prerequisite split and requirements; they have not yet accepted every
field, clipping policy, explicit-configuration exception or locking detail here.

## Local integration update — 2026-11-20

The earlier #3064 working tree remains preserved. The separate local
`codex/rem-source-three-provider-integration` branch in
`connectonion-rem-source-integration` now contains candidate source-owned adapters
against this shared contract and the current #3223 revision. These adapters are
not included in the shared prerequisite. Their user-run offline checks passed
on 2026-11-20; real accounts and installation migrations remain unverified.

Shared changes from exercising the adapter shapes: preserve removal of a selected
project through the generic configure entry point, allow an empty selection to
disable its source, and reject an outdated configuration write when another
operation changed the selection during metadata validation. Synthetic tests cover
these cases. This local implementation does not transfer migration ownership
from the Asana or Granola teams.
