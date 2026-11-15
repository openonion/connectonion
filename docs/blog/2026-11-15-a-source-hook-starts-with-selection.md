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

The first prototype used two synthetic providers to exercise the contract. This
local follow-up connects one real provider, Obsidian, so the lock, consent and
model-retry boundaries can be reviewed with working call sites. Migrating every
provider at once would entangle the interface decision with all their storage
and acquisition behavior. Asana and legacy kinds remain separate migrations;
#3040's full acceptance criterion is not yet met.

See the [interface proposal](../rem/source-interface.md) for signatures,
lock and approval responsibilities, migration steps and validation commands.


## Initial Obsidian integration

The single-vault worktree now exercises this proposal through public source
configuration, consent, sync, investigation and reader citations. It also adds
metadata-only pending counts and checks retained material on subsequent model
attempts. The author has run the targeted tests and a live walkthrough; the broader
regression still has unresolved failures recorded in the validation guide. These
changes do not migrate Asana or every legacy kind, or imply agreement on #3040.

The live investigation exposed a separate boundary: disabling other subscriptions
did not stop the shared runner from retrieving Codex sessions and searching the web.
Selected-source gathering and independent agent retrieval are different paths.
The proposal does not yet enforce source-only execution for that runner.
