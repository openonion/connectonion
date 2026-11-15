# Selected REM source interface — draft integration

This is a proposed implementation for [#3040](https://github.com/openonion/connectonion/issues/3040),
not an approved public API. This local single-vault branch includes the saved-version
foundation from [#3055](https://github.com/openonion/connectonion/pull/3055)
(`784d00a5ecddd99dd0a0f0b3cc368d337833dd50`) and the local interface prototype.
Obsidian is the first registered provider. Asana #3060 has not been migrated here.

## Dispatch from selection

`source_hooks.MODULES` contains module paths, not imported objects. The dispatcher
reads saved notebook subscriptions and loads only registered, enabled selections
that are not unsubscribed. Metadata describes saved configuration. Imports,
`status` and `consent` must not read source bodies, decrypt credentials or use the
network. This is a provider contract enforced by tests, not a Python sandbox.
Legacy source discovery still follows its existing path; this draft does not
claim that all existing providers meet the new contract yet.

| Hook | Responsibility |
| --- | --- |
| `configure(root, **options)` | Save an explicit selection; invalidate approval when scope changes. |
| `status(subscription)` | Describe configured scope without probing it. |
| `consent(subscription)` | Describe acquisition and model use. |
| `pending(root, subscription, progress)` | Inspect saved counters without reading bodies. |
| `fetch(root, subscription)` | Acquire snapshots from the selected source. |
| `collect(root, subscription, progress, max_items, max_chars)` | Return an offline `Batch` and proposed progress. |
| `gather(root, subscription, handles, start, record)` | Search saved material and return items and coverage. |
| `record_of(source_id)` | Parse namespaced record identity without I/O. |
| `cited(root, subscription, source_id)` | Return an exact saved version within current scope. |

The CLI routes registered source configuration through the provider. Sync acquires
snapshots before its stage transaction, then consumes bounded offline batches.
Native rounds acquire before opening a new round. Investigation searches snapshots;
it does not silently refresh the live vault. A notebook with no selected Obsidian
source gets no Obsidian import or coverage line from this dispatcher.

## Approval and transactions

Content requires an active boolean consent flag and a matching scope, runner and
model in REM's existing consent receipt. A flag alone grants nothing. The Obsidian
store checks this again after acquiring its lock. Removing a source or changing
scope invalidates retained material for subsequent model calls and citations.
A request already sent to a model cannot be recalled by a later revocation.

This boundary controls material supplied through the source hooks; it is not a
sandbox for the shared investigation runner. The local Obsidian walkthrough also
produced Codex-session citations and web searches from that runner. Subscription
selection alone therefore does not enforce source-only investigation execution.

Acquisition owns its transaction. `collect` returns proposed progress without
persisting it; the stage commits progress only when work is kept. Expected file
availability failures become explicit acquisition results. Programming errors,
invalid schemas and corrupt stores propagate instead of appearing as empty data.
If acquisition fails, approved saved snapshots may still be consumed; the CLI
reports that acquisition failed rather than claiming the snapshots were refreshed.

Offline hooks can run within a stage's notebook transaction. `material_lock`
reuses only a lock owned by the same process and thread for the exact notebook.
Ordinary maintenance locks remain non-reentrant. Retained task items, extracted
source IDs, original-evidence files and native prior material are rechecked before
use. Model follow-ups, timeout retries and child citation/insight audits are guarded.

## Exact versions and compatibility

The imported #3055 revision is `784d00a5ecddd99dd0a0f0b3cc368d337833dd50`.
Besides version routing, that dependency includes the no-change sync Next/log
fix and project-to-agenda lead routing. Those generic fixes and their tests are
retained as prerequisite work, not introduced as Obsidian-specific behavior.

The optional `resolve=` argument on #3055's version helpers provides notebook-scoped
routing. Registered kinds never fall back to global callbacks when deselected.
Explicit legacy callbacks remain for kinds not yet migrated. The import-all
`PROVIDERS` list is removed: it would load a provider before notebook selection.

`cited` returns `None` for an unavailable version, never the latest version instead.
Its context uses the reader's existing excerpt/time/sender/thread/source fields.
Source modification time and snapshot capture time remain separate. Replacement
matching means another version of the same record, not proof that it is newer.
A rollback can therefore replace a citation too.

The reader and citation-preservation paths now receive notebook context. Source
IDs also remain attached to extraction and investigation wrappers. Private-labelled
Obsidian notes are omitted; the contract has no owner-only visibility override.

## Remaining design decisions

This draft demonstrates one provider end to end. It does not claim the full #3040
migration is complete. Before declaring the API stable, agree the hook signatures,
acquisition failure policy, owner-only visibility, shared investigation budgets,
independent runner retrieval, and migration of existing source paths. Asana should move token access into fetch
and keep metadata offline, but its implementation needs a separate coordinated
change. CLI configuration options may also need a smaller provider-neutral shape.

See [Obsidian snapshots](obsidian-snapshots.md) and [validation](obsidian-validation.md).
The author reports the targeted integration tests passed locally. The broader
regression has unresolved failures; see the validation record. No tests were run
by the implementation agent during the submission-scope review.
