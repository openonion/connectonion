# Shared REM source contract for Obsidian, Asana and Granola

Local implementation candidate, 2026-11-19. The teams support a shared prerequisite PR and
source-owned migrations. The exact signatures and policies below are proposed
for that PR. Discussion evidence, implementation gaps and PR ownership are in
the [coordination record](source-interface-coordination.md). The
[implementation overview](source-interface.md) describes the extracted local code.
Exact policy choices remain subject to team review. Shared and separate local-adapter
offline test results are recorded in the [validation note](source-interface-validation.md).
Those results do not certify a live-service migration.

## Contract and ownership

The shared layer owns selection, approval checks, routing, cross-source budgets
and transactional publication of accepted progress. An adapter owns scope
validation, acquisition, snapshot storage, matching and exact-version decoding.
Each registered kind names a module of ordinary functions. The registry stores
module paths. Notebook configuration cannot supply an
arbitrary import path.

The proposed adapter surface is shown below. `Batch` is the existing REM type.
`subscription` contains the saved scope and non-secret identity. Return dictionaries
use the documented fields below. Existing provider helpers may be wrapped to
satisfy the contract while preserving their standalone callers.

```python
class Source(Protocol):
    kind: str
    skill: str

    def configure(self, root: Path, **options) -> dict: ...
    def status(self, subscription: dict) -> dict: ...
    def consent(self, subscription: dict) -> str: ...
    def pending(self, root: Path, subscription: dict, progress: dict) -> dict: ...
    def fetch(self, root: Path, subscription: dict) -> dict: ...
    def collect(self, root: Path, subscription: dict, progress: dict,
                max_items: int, max_chars: int) -> Batch: ...
    def gather(self, root: Path, subscription: dict, handles: list[str], *,
               start: datetime, end: datetime | None, record: str,
               owner: bool, max_items: int, max_chars: int
               ) -> tuple[list[dict], list[str]]: ...
    def record_of(self, citation_target: str) -> str | None: ...
    def cited(self, root: Path, subscription: dict,
              citation_target: str) -> dict | None: ...
```

`skill` must be `rem-source-<kind>`. Prompt composition uses this conventional
path without importing a provider merely to measure or load its instructions.

`configure` validates explicit user options and returns the saved selection.
The adapter does not persist the selection itself. The shared selection writer owns the subscription transaction and
clears approval when the account or scope expands or changes. Metadata needed
to describe the selection is saved with it, including display names, account or
profile, folders/projects and relevant scope flags. An explicit connection
operation can validate remote identity or folder metadata. It cannot read note
or task bodies before approval. Unsupported options fail before acquisition.
The shared writer compares the selection before and after validation; a
concurrent removal or edit wins and the older configure request must retry.
An adapter may return `enabled: false` when removing its last project. This
disables the source and clears consent. `remove --project ID` delegates
`remove=True, project=ID` to the configuration hook; unsupported sources reject
it. Partial removals conservatively require approval of the new scope.
Granola acquisition is limited to generated summaries in the approved personal
folder or selected note. Its team explicitly excludes transcripts, private
notes, audio and attachments, including when they fall inside the selected scope.

`status` and `consent` read their argument only. They do not decrypt credentials,
open snapshot bodies or call a service. `pending` returns `count` as an integer
or `None`, with `body_reads: false` and a short explanation for unknown counts.
A missing body-free count index produces an unknown count. Empty known work
produces zero. Inspecting pending work cannot consume a checkpoint.

## Selection and approval lifecycle

| State / operation | Shared behavior |
| --- | --- |
| Unconfigured or unselected during ordinary REM work | Skip imports, acquisition and investigation coverage for that kind. |
| Disabled | Show saved disabled state when explicitly inspecting sources. Skip provider imports and content operations. |
| Selected, awaiting approval | Render saved names and scope through generic metadata formatting. Skip provider imports, bodies and acquisition. |
| Selected with valid approval | Load the selected adapter for the requested operation. Recheck current scope before exposing material. |
| Explicit add/connect/configure | Load that requested configuration implementation to validate and save the selection. Source-body acquisition still requires approval. |
| Dry-run | Skip fetch and the model. Read approved saved counters where available and leave progress unchanged. |
| Removal, revocation or account/scope change | Deny subsequent content dispatch and retained-evidence use until the current selection is approved. |

The explicit configuration row is a proposed interpretation for team review.
Granola requested no imports before consent. The earlier #3064 candidate imported
adapters to display status and consent before approval. Generic saved-metadata
rendering is implemented in this extracted candidate and its local integration. The explicit
configuration entry point needs an exemption to that passive-import rule so a
user can configure a new source. This exemption has not been accepted in #3040.

The extracted shared display always uses saved metadata; it does not call adapter
status/consent hooks. Those metadata-only functions remain available to source-owned
callers. The shared summary includes the full effective scope and stays identical
before/after approval, avoiding repeated consent prompts caused by display changes.

The notebook consent receipt stores `source_approvals` separately from the
mail/session summary. Each entry binds a source scope to the default runner/model
and every effective stage runner/model, including level settings and explicit
routes. The same `source_execution` map appears in the confirmation summary;
the CLI groups stages that use the same recipient. Old registered-source approvals
without this map require a fresh confirmation, never an automatic upgrade.

Before confirmation, save default source metadata under a short lock so a relative
lookback does not drift while the user reads it. The final approval transaction
compares the displayed snapshot before subscribing the mailboxes it offered. A
changed selection or model route rejects that confirmation. Automatic init/mail
grants preserve registered-source approvals, including approvals that have become
invalid; `start` checks those entries independently and requests confirmation again.

Check it again during acquisition publication, batch consumption, investigation,
cached citation resolution and resumed model work. A registry entry or citation
routing record cannot grant access. Configuration, removal and commit-time
approval checks use the same short notebook transaction.

Prepared source-backed tasks retain the execution map captured at preparation,
not a later refreshed map. Dispatch, retries and resumed tasks reject a changed
map even if the new configuration has since been approved. Preparation also checks
the actual stage runner/model; dispatch checks the actual recipient. An explicit
render route is recorded as the render stage when investigation hands over to it.
Reprepare old source-backed tasks after changing routes instead of silently
retargeting a cached task. This check is skipped for material without registered
source references, preserving the legacy task paths.

## Acquisition, failure and progress

The caller captures the approved selection, releases the notebook lock, then
calls `fetch`. A local adapter may scan selected files. A remote adapter may
fetch approved source material. The adapter serializes its snapshot updates
under its storage lock and rechecks account, scope and approval before publishing.

The implemented acquisition lock order is storage writer lock, then short notebook
commit guard. Network work runs outside the notebook lock. Offline hooks run under
the notebook boundary and **must not wait for the acquisition writer lock**. They
read atomically published immutable snapshots/indices or committed byte ranges.
A store needing a blocking writer lock for reads must adapt its publication/read
strategy before using these hooks. This concrete restriction resolves a lock inversion
found during static review and needs team review. The synthetic interleaving test
models a writer waiting to publish while a reader consumes the previous snapshot.
Each adapter must supply its own concurrency and revocation evidence.

Native acquisition uses the preparation progress watcher and deadline before the
long notebook lock. A short preflight lock checks repeated-stall holds and preserves
the prior preparer's identity when waiting for another native task. Fresh catchup
nights and explicit discard acquire again; an open pending task keeps its saved
material. The collection-only held path may acquire without spending a model call.

| Result | Proposed action |
| --- | --- |
| Successful acquisition | Publish complete snapshots and a scope-bound success receipt, then allow offline consumption. |
| Expected temporary availability failure | Report the failure. Allow prior saved material only after current approval, account, scope and integrity checks pass. Mark its use as stale. |
| Account, authorization, scope or integrity failure | Block content from that source, including retained citations. Preserve the failure receipt until a successful validated acquisition repairs it. |
| Unexpected implementation error | Propagate the error with diagnostic context. |

Adapters translate known acquisition failures to `SourceUnavailable` and classify
whether saved material remains usable. A later temporary failure cannot erase
an existing account/integrity block. Expected source failures remain visible
while other eligible sources continue. Messages expose no credentials or bodies.

Every acquisition receipt has a unique ID. A success cannot clear a blocking
receipt that changed after that acquisition began; it returns a blocked result
and preserves the failure. A fresh retry started after the block can clear it.
Overlapping failures conservatively win, including a failure published after an
overlapping success. This requires a new retry rather than inferring recovery from
completion order. Receipt comparison/publication uses the short notebook lock;
no notebook lock is added around provider acquisition or network work.

`require_material` raises `SourceMaterialUnavailable` (a `RemError`) when retained
material no longer passes the current access check. Native submit translates that
specific failure into its existing `TaskFault`, so the driver can park the stale
task. Other notebook I/O or ownership-data errors propagate as round errors.

Granola partial refreshes need an explicit adapter decision about atomic
publication. The local candidate publishes only a complete selected acquisition.

`collect` reads saved material and returns a `Batch` with proposed progress.
The caller supplies a copy of progress and owns persistence. Snapshot acquisition
and REM consumption have separate checkpoints. Rejected or interrupted model
work cannot advance the consumption checkpoint. Persist routing metadata for validated evidence before a retained task or page
first references it. This metadata write does not advance consumption progress.
After accepted work, publish page changes and consumption progress together
using the existing recoverable notebook transaction.

An empty batch may propose metadata progress, such as recording a validated
withdrawal. The caller must distinguish this from an acquisition failure and
commit it only through the same accepted-work policy. Retries must preserve
all unprocessed material.

## Budgets and investigation

The draft uses positive integer item and character limits. Character cost is
the sum of `len(json.dumps(item, ensure_ascii=False))` across emitted items,
including citation and metadata fields. All callers and adapters must use this
same accounting function. These are material limits, not model token limits.

Proposed oversized-item policy follows the local candidate. Defer an item when
it does not fit after earlier items. An oversized first item may have its text
explicitly clipped, with a truncation marker and its full original citation
retained. Preserve identity, scope and visibility checks before clipping. If the
metadata plus marker cannot fit, report budget exhaustion and leave its
checkpoint intact. The teams have agreed to explicit limits, while this clipping
policy remains a draft choice.

`gather` consumes one remaining budget across all selected approved providers.
The shared caller passes the remaining allowance to each provider and validates
the result. Use timezone-aware timestamps and the interval `[start, end)`.
`end=None` means no upper bound. Each provider reports which saved timestamp it
uses and any coverage limits. Gathering changes no sync progress and performs
no remote refresh.

`owner=True` carries the caller's request for owner-related evidence. Asana can
use its verified account and supported assignment/author rules. Obsidian and
Granola must disclose absent authorship evidence rather than treating a name
mention as proof. A provider lacking that capability returns no owner-evidence
items and an explanation for the selected approved source.

Granola can reject `--since`, `--only` and `--force` during configuration while
filtering saved investigation candidates by their recorded timestamps. Those
are different operations. Independent retrieval by the investigation runner
needs its own execution policy. The hooks govern the material they supply.

## Stable identity and exact citation target

Preserve three distinct facts. `kind` selects the adapter, `record_id` identifies
the continuing record within its account/vault, and `citation_target` identifies
the saved version. The proposed batch representation retains the existing
`source` field for the citation target and `source_kind` for the adapter kind.
The adapter's `record_of(source)` derives the stable record ID.

| Provider | Stable record identity | Exact citation target |
| --- | --- | --- |
| Obsidian | Vault instance plus note identity | Existing `obsidian:` ID with saved version identity. |
| Asana | Account plus task identity | Existing `asana:<account>:<task>:<file>:<offset>` ID. |
| Granola | Existing `granola:<profile>:<note-id>` record ID | Existing `adapter:docs/granola/...jsonl#granola:<profile>:<note-id>?version=<sha256>`. |

Granola already binds its references to a hash of the complete record except
`fetched`. Its resolver checks the saved record ID and hash. The old reference
stays valid after a later version is appended. Its unit test covers that
behavior. These are inspected implementations and test definitions, not new
test results. [Reference creation and resolution](https://github.com/openonion/connectonion/blob/544d79d680dc097dce6d0db62b96957f722f237d/connectonion/useful_tools/adapter.py#L278),
[old-citation test](https://github.com/openonion/connectonion/blob/544d79d680dc097dce6d0db62b96957f722f237d/tests/unit/test_rem_granola_remote.py#L109).

### Proposed routing for persisted pages

Pages retain citation strings across runs, after their in-memory `source_kind`
has disappeared. Preserve the original citation target and persist a
notebook-scoped routing entry linking it to `kind`, stable record ID and source
subscription identity. Derive this entry from validated adapter output, never
from model-supplied fields. Reject conflicting ownership for the same target.
Store the entry transactionally before persisting a task or publishing a page
that cites it, so retries and pre-publication citation checks can resolve it.
Keep the entry when a source is removed, with current approval still gating reads.

The shared `record_of(root, target)` and `cited(root, target)` wrappers resolve
the entry, check current selection/approval and dispatch to that adapter with
the original target. A known unique source-qualified prefix can retain the
existing #3055 routing path. A generic `adapter:` prefix requires an explicit
owner. Never map every `adapter:` reference to Granola or probe all providers.

For older imported pages that lack a routing entry, a source-owned migration may
register validated references from its approved store. Unknown ownership stays
unresolved. Source-owned migrations can validate old targets through
`remember_material` while holding `material_lock`; raw metadata cannot grant access. The former local candidate's provisional
`granola:docs/...` references require source-owned compatibility. The separate
November 20 integration implements a read-only alias and adopts validated
canonical historical targets. The user-run offline integration checks passed; no
real installation was migrated. The candidate stores an object in
`.state/source-citations.json`, keyed by the
complete target, with `kind`, `record` and `subscription` string fields. `collect`
and `gather` validate all entries and atomically write them under the notebook lock
before returning material. A conflicting owner rejects the whole update. A missing
registration cannot release a retained task from its approval checks. Reader/review
operations cache only ownership for their duration and recheck approval for every
resolution. The format and publication boundary remain reviewable API choices.

`cited` enforces the current account, folders/projects, visibility and integrity
before returning the saved excerpt. A missing or revoked version returns `None`.
Versioned lookups never substitute another saved version. Preserve the existing
reader context fields, including `excerpt`, `truncated`, `time`, `sender`,
`thread`, `source` and `subject`. Capture time may be provided separately.

`record_of` parses identity without I/O. Replacement matching uses `(kind,
record_id)`, including the account/vault in `record_id`. In #3055, `superseded`
means replaced by another version of the same record, including a rollback.
It does not establish chronological recency.

### Citation formatting

Granola supplied this regression-form spelling, with the hash abbreviated here.

```text
Sources: [1] adapter:docs/granola/daily/2026/11/08.jsonl#granola:personal:not_example?version=<64-hex-sha256>
```

Normalize the surrounding Markdown into the Reader's source-definition form.

```text
## Sources
- [1] adapter:docs/granola/daily/2026/11/08.jsonl#granola:personal:not_example?version=<64-hex-sha256>
```

Run this generic formatting step before unresolved-citation filtering. Preserve
every target byte, including the hash, and require exact resolution afterward.
Normalization and provider routing are separate operations. Validate the exact
inline example, ordinary source sections, repeated normalization and malformed
references. A synthetic regression hash must be 64 hexadecimal characters.

## Compatibility acceptance cases

| Case | Required observable result | Evidence owner |
| --- | --- | --- |
| Selection and import isolation | Unselected, disabled and awaiting-consent sources cause no passive adapter imports or unrelated coverage. Explicit configuration follows the documented exception. | Shared tests plus all adapters |
| Metadata and dry-run | No body reads, key decryption, network calls, model calls or consumption progress writes. Unknown pending counts remain unknown. | Shared plus each adapter |
| Lock and revocation | Fetch has no long-lived notebook lock. Scope change during acquisition prevents publication and retained-material use. | Shared plus each store |
| Failure and retry | Temporary stale use is visible. Integrity/account blocks survive a subsequent temporary failure. Other eligible sources continue. | Shared plus each adapter |
| Batch acceptance | Strict item/character limits, explicit truncation, deferred items and rejected-work retry preserve progress correctly. | Shared plus each adapter |
| Gather | End time exclusive, owner semantics explained, aggregate budget enforced, saved material only. | Shared plus each adapter |
| Exact versions | Resolve A, save B, then resolve A and B independently. A missing hash and revoked scope cannot resolve. | All adapters |
| Persisted routing | Restart and resolve `adapter:` targets without importing unrelated sources. Conflicting ownership fails. Migration handles old page references explicitly. | Shared plus Granola |
| Same-record replacement | Account/vault collisions cannot suppress lost evidence. Preserve #3055 replacement behavior. | Shared plus Asana/Obsidian |
| Citation spelling | Granola's inline spelling becomes a valid definition with unchanged target, survives filtering and resolves. | Shared plus Granola |
| Granola selection | Fetch only approved personal folder/note generated summaries. Exclude transcripts, private notes, audio and attachments. Reject unsupported since/only/force flags. | Granola |
| Generic-stage integration | Public CLI, sync, investigation, Reader and retained-task paths use the shared boundary and preserve existing behavior. | Shared integration tests |

The extraction is scoped to meet #3040's static acceptance check.

```bash
rg -n 'asana|obsidian|granola' \
  connectonion/rem/{runner,investigate,daily,native,native_round,leads}.py
```

No matches are expected. Execute behavioral tests on the extracted branch before
claiming compatibility. Document both the checked revision and actual results.
