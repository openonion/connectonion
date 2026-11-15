# Selected REM source interface — local proposal

This prototype implements a module contract and dispatcher for the discussion
in [#3040](https://github.com/openonion/connectonion/issues/3040). It is based on
[#3055](https://github.com/openonion/connectonion/pull/3055), commit
`784d00a5ecddd99dd0a0f0b3cc368d337833dd50`, and reuses its saved-version helpers.
The contract is a proposal, not a maintainer-approved API.

No production source is registered yet. The public CLI, runner, investigation,
daily rounds and reader have not been switched to this dispatcher. Existing
callers of #3055's version helpers continue to work. The two fictional providers
in `test_rem_source_hooks.py` exercise the new boundary without credentials,
network access or a real vault.

## One module, one registration

`connectonion.rem.source_hooks.Source` is a structural protocol: a module of
ordinary functions can implement it. No base class or import-time registration
is required. `MODULES` maps each kind to its module's import path. Adding a kind
eventually adds one entry there, rather than a branch in each REM stage.

The dispatcher reads the notebook's saved `subscriptions.json`. It includes
only registered, enabled subscriptions that are not unsubscribed. It never
discovers accounts, probes vaults or fabricates defaults. Import paths come
from code, never from notebook JSON. A citation loads only its matching kind.
There is no global cache of notebook selection or approval. Python caches a
successfully imported module; a failed import can be retried.

| Hook | Inputs beyond the selected subscription | Responsibility |
| --- | --- | --- |
| `status` | none | Describe names and configured scope only. |
| `consent` | none | Describe what the user is being asked to approve. |
| `fetch` | notebook root | Acquire and save snapshots; may read selected local files or call an API. |
| `collect` | root, progress, item and character limits | Read saved material into the existing `Batch`; return proposed progress. |
| `gather` | root, handles, start time, target record | Search saved material and return items plus coverage lines. |
| `record_of` | source ID only, no subscription | Parse a stable, namespaced record identity without I/O. |
| `cited` | root, exact source ID | Return the specified saved version within the supplied current scope. |

Compared with the Asana proposal in #3040, data methods receive the notebook
root explicitly. `cited` also receives the current subscription, so a provider
can enforce the exact selected folders/projects, including multiple named
subscriptions of one kind. This avoids hidden notebook globals. `record_of`
and `cited` on an existing provider can remain small internal helpers, with a
scope-aware wrapper implementing this contract.

Imports, `status` and `consent` must not decrypt credentials, access source
storage or use the network. This is an adapter contract, not a Python sandbox.
Adapter tests must enforce it with filesystem/network/credential spies.

## Approval and storage boundaries

Metadata is available before approval. Content dispatch requires `consented`
to be the boolean `true` as well as an active selection; string flags are
rejected. Configuration writers must clear consent whenever scope changes.
Providers must revalidate the supplied scope at the actual storage boundary
under their storage lock, especially if configuration can change concurrently.

These gates do not replace REM's complete consent-summary/fingerprint protocol.
The stage caller still needs to verify notebook approval before exposing
material to a model. Wiring that policy, the consent UI and configuration
writers into the shared path is a separate integration step. This prototype
does not introduce a second approval file or grant permission itself.

Call `fetch(root)` before taking a long-lived REM notebook lock. Each provider
owns the short transactions needed to save its snapshots and recheck scope.
An adapter may translate an expected availability failure into
`SourceUnavailable` with a safe explanation. The dispatcher records that
failure and continues other sources. It does not catch `KeyError`, `TypeError`,
arbitrary `RemError` or corrupt-store failures.

`collect(root, name, progress, max_items, max_chars)` never acquires new source
material. It passes a deep copy of progress to the provider and returns the
provider's existing `Batch` type. Items use the existing REM `source` citation
field and `text`, with timestamp/reference/project metadata where applicable;
the snapshot store's internal `source_id` field is not a new batch schema.
The provider enforces both limits and must
not persist the caller's checkpoint. The stage persists `Batch.progress` only
when the corresponding work is kept; failed work can consume the same batch
again. The stage owns that transaction and must not hold it across networking.
The dispatcher has no automatic scheduler or fetch/collect orchestration.

`gather` searches only approved selections. A notebook with no selected source
gets no source-specific coverage line. Unlike acquisition, corruption while
reading saved evidence propagates instead of becoming "nothing found".

## Citation compatibility with #3055

The new optional `resolve=` argument on `source_versions.record_of`, `cited`
and `superseded` supplies a notebook-scoped prefix lookup. `source_hooks`
provides that resolver. It never falls back to the old global callback
registry when a source is unselected. #3055's global `register` API remains
for existing callers while their notebook context is threaded through.
The old import-all `PROVIDERS` list is removed; provider migrations must use
`source_hooks.MODULES`, not import-time callback registration.

`cited` returns `None` for a missing or out-of-scope version. It must never
substitute the latest version. Its context includes the reader's `excerpt`,
`truncated`, `time`, `sender`, `thread`, `source` and `subject` fields; optional
capture time and scope descriptions can be retained. There is no owner-only
visibility argument yet, so providers must omit private-labelled content by
default, as the local Obsidian adapter does.

The provider's `record_of` must include notebook/vault or account and record
identity as needed to avoid collisions within its kind. Shared replacement
matching also includes the source prefix, so equal local IDs from different
kinds cannot hide lost evidence. The provider parser does no I/O; the router
reads notebook selection before dispatching it. It proves neither that a version exists nor
that one version is newer. #3055's `superseded` means replacement by another
version of the same record, including a rollback to an older version. A true
chronological rule would need an explicit saved sequence, not a UUID comparison.

## Adapting the local Obsidian work and Asana

Keep provider implementation commits on their own branches. The existing
single-vault Obsidian branch has configuration, scoped reads, snapshot storage
and version adapters, but is not copied into this interface branch.

For Obsidian, the current `obsidian_store.collect(root)` scans the selected
vault and stores changes. It belongs behind **fetch**, despite its current
name. Implement the hook's **collect** separately: read saved changes after
the checkpoint, fit the batch limits, and return proposed progress. Add an
offline gather implementation over approved saved material. Wrap existing
`record_of` and `cited` with the supplied-scope validation for this contract.
Keep source timestamps distinct from capture timestamps.

For Asana, move token access and remote acquisition behind **fetch**. Metadata
uses saved names only; collect/gather/cited use retained local versions. Its
concrete adapter must be checked against the friend's implementation before
registration; this branch does not claim to have migrated it.

Next, agree the contract in #3040, adapt the two real providers, and migrate
existing kinds plus stage callers to the shared dispatch. Only after that
should #3040's "source module, CLI, tests and one registration line" acceptance
criterion be claimed. Existing `page_review` functions lack notebook context;
they still use #3055's unscoped callback path in this prototype.

## Validation to run locally

Run `test_rem_source_hooks.py` and `test_rem_source_versions.py` first. Then run
`test_rem_page_review.py` and `test_rem_reader_model.py` for the existing callers.
The first group covers selection isolation, consent gates, exact versions,
scope changes, expected acquisition failures, checkpoint ownership, and import
retry. These tests have been written but not run as part of this local change.
