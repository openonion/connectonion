# A source hook starts with selection

Design journal draft. This local proposal is based on #3055 and responds to
#3040; it has not shipped and the interface has not been approved.

Three sources needed to enter REM at the same places: acquisition, batch
reading, investigation and citations. Adding a provider-specific branch at
each place makes every source author edit the same generic files. More
subtly, discovering every provider before choosing one can decrypt a token or
scan a vault for a notebook that never selected it.

The proposed boundary starts with saved selections. A small registry stores
module paths, and dispatch imports only the selected kind needed for the
operation. Metadata describes names before approval. Content operations need
an active approved selection and pass its scope to the provider. This is an
adapter contract, not a sandbox: provider modules must keep imports and
metadata free of source I/O, and tests need to prove that behavior.

Acquisition and consumption have different lifetimes. A network API call or a
vault scan produces saved snapshots. A REM batch consumes those snapshots and
offers a checkpoint which the caller commits only after keeping the work.
The existing Obsidian snapshot collector therefore fits the acquisition hook;
using it as the batch hook would rescan the vault during offline processing.

The version helpers from #3055 can accept a notebook-scoped resolver rather
than growing a second global registry. A cited version stays exact. Record
identity tells us two citations refer to one task or note; it does not tell us
which version is newer. That distinction matters when version IDs are UUIDs.

An alternative was to migrate all REM stages and both providers in this first
change. That would entangle the interface decision with storage, approval and
model scheduling changes. This draft instead makes the contract executable
with two synthetic providers and leaves existing callers working. The cost
is explicit: production stages still need migration, and #3040's acceptance
criterion is not yet met. The next review should decide the contract before
the Asana and Obsidian adapters depend on it.

See the [interface proposal](../rem/source-interface.md) for signatures,
lock and approval responsibilities, migration steps and validation commands.
