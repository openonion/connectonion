# Shared REM source hooks

This local prerequisite candidate implements the shared boundary discussed in
[#3040](https://github.com/openonion/connectonion/issues/3040). It builds on the
saved-version foundation in [#3055](https://github.com/openonion/connectonion/pull/3055),
commit `784d00a5ecddd99dd0a0f0b3cc368d337833dd50`. That PR was still open when
checked on 2026-11-20. The exact API choices remain reviewable on the shared PR.

The public source CLI, manual/native sync, investigation, page review, retained
model work and Reader now call the shared boundary. No production provider is
registered in this prerequisite. Each team adds its own implementation and one
registration in its migration PR. Existing built-in mail/session/chat paths keep
their current behavior.

- [Contract and lifecycle](source-interface-contract.md)
- [Three-team coordination and migration ownership](source-interface-coordination.md)
- [Validation commands and scope](source-interface-validation.md)

## Add a module, then register it

`source_hooks.Source` describes ordinary module functions. `MODULES` contains
module paths declared in code, never arbitrary paths supplied by notebook JSON.
A fictional registration is:

```python
MODULES = {"notes": "connectonion.rem.notes_source"}
```

`skill` must be `rem-source-<kind>`. Prompt composition uses this conventional
path without importing a provider merely to measure or load its instructions.

`configure(root, **options)` returns saved, non-secret selection metadata. The
shared writer persists it and clears approval when scope changes. The generic
CLI forwards explicit options, including `--project`, `--vault`, `--folder`,
`--since`, `--only`, `--force`, `--replace`, `--config` and `connect=True`.
Removing a selected project forwards `remove=True, project=ID`. An empty scope
can return `enabled=False`; the shared writer disables it and clears consent.
Configuration is saved only if the previous selection has not changed during
validation, so a slow request cannot undo a concurrent removal.
The adapter validates supported combinations; shared stages do not branch on
provider names. An adapter migrating from the local #3064 candidate must stop
saving the selection inside `configure` and return the validated selection.

The shared metadata display renders saved names and full scope without importing
an adapter, even before consent. Adapter `status` and `consent` functions remain
metadata-only functions available to source-owned callers; the shared approval
summary deliberately uses one stable generic rendering before and after approval.
Explicit configuration is the sole pre-approval import exception. It may validate
connection metadata but must not acquire note/task bodies.

## Acquire, consume and retain evidence

`fetch` runs before the long-lived notebook lock. The adapter owns acquisition
serialization and must wrap final publication in `acquisition_guard(root, sub)`.
It publishes complete immutable snapshots or committed byte ranges plus an
atomic index. The network phase never holds the notebook lock.

`collect`, `gather`, `pending` and `cited` run under the notebook read/commit
boundary. They must read committed state without waiting for the acquisition
writer lock. Otherwise a writer holding that lock while waiting to publish could
deadlock with a notebook reader. The contract documents this adapter obligation;
it is not enforced by a Python sandbox.

`collect` gets copied progress and strict item/serialized-character limits.
A first oversized item's text may be explicitly clipped; later items are deferred.
The returned `Batch.progress` is only a proposal. Existing REM acceptance paths
own consumption progress; failed work remains retryable. `pending` reads counters,
not bodies; an unavailable count is `None`, not zero.

`gather` receives aware start/end times, owner context and remaining shared
budgets. It reads saved material only. Unselected, disabled and unapproved
providers produce no imports or unrelated investigation lines. This contract
controls material supplied by hooks; it does not sandbox the runner's independent
web or local retrieval.

## Exact citations can have a different prefix

A batch item names its immutable target in `source`; an opaque target also needs
`source_kind`. For example, the kind `summaries` may emit:

```text
adapter:docs/summaries/daily/2026/11/19.jsonl#summaries:personal:note?version=<64-hex-sha256>
```

Before evidence is retained, the shared layer validates `record_of(target)` and
`cited(root, current_subscription, target)`, then records its owner in
`.state/source-citations.json`. The complete target is the key; values contain
`kind`, `record` and `subscription`. No credentials or body text are stored there.
This write does not consume progress or mean a page update was accepted.

The routing table survives restart/removal. Reader and retained-task checks still
require current scope/model approval and the exact saved version. Unknown
`adapter:` ownership stays unresolved; the router never tries every provider or
falls back to a global resolver for a managed target. Existing unique
source-qualified targets can route without a table entry. A source-owned migration
can register validated old targets through `remember_material` while holding the
notebook boundary. The separate integration candidate retains a source-owned compatibility reader
for the older local candidate's `granola:docs/...` citations. Canonical new targets
retain Granola's `adapter:` spelling. No provider-specific alias is built into
the shared router.

Page normalization changes only Sources headings/list spelling, preserving every
target byte. Routing and normalization are separate. Same-record replacement uses
`(kind, record_id)` and retains #3055's rollback semantics; it does not infer time
ordering from a hash or UUID. Lookup caches ownership only within one operation;
authorization is never cached across Reader or model calls.

## Evidence status

Synthetic fixtures represent a version-qualified note, a task file/offset and an
opaque path/hash target. The tests cover dispatch, public integration, current
approval, restart, failure handling, strict limits and progress. They do not prove
that any real provider has completed migration or passed its own scope tests.

No tests or `co audit` were run during this extraction, at the user's request.
No commit, push or PR creation was performed. Run the commands in the validation
note before reporting test results for this candidate.
