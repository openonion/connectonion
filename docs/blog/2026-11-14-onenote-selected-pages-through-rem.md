# Selected OneNote pages through the existing REM lifecycle

OneNote already had browsing and page creation. A source integration also needs
an explicit selection, reliable local versions and evidence that remains readable
after a note changes. This change adds that intake without a separate scheduler
or a source-specific Reader category.

Connecting OneNote lists metadata and pins an account, notebook, section and page
selection. It does not approve body reads. Init/start retains the existing REM
source/model approval boundary; disabled OneNote needs no authorization. Approved
init/sync collects the selected bodies, then normal REM Skills organize evidence.
The existing timers dispatch sync, and opening Reader never triggers collection.

Relying only on Graph modification times would make imports cheaper, but could
miss a changed body whose timestamp did not advance. Native sync instead rereads
every selected body and deduplicates by content. This costs selected-page GETs on
every sync. The manual import command retains timestamp-based skipping plus an
explicit `--full` diagnostic path. Neither path discovers additional page bodies
implicitly or downloads media bytes.

Local JSONL snapshots carry canonical record identity and scope. Citations pin a
content version, so appending a later snapshot cannot change earlier evidence.
Reader resolves a bounded, sanitized context; claim review reads the full pinned
record within its evidence budget. Disposable Reader responses alias internal
citation identities and omit OneNote credential-file/home metadata, while stored
records and consent remain unchanged.

The current REM writer checks for credential shapes when saving a page. The
forward-port review caught an earlier boundary: an imported record could carry
a key into the model request before any page write. The same detector now stops
that handoff and withholds affected Reader fields. A synthetic regression checks
both paths and confirms the immutable local version survives the refusal.

The feature was extracted from the team OneNote branch and forward-ported to the
current upstream REM interfaces. Copying the mixed adapter or older shared REM
files would also import sibling providers or discard newer runner, page and
authorization contracts. Only the generic record primitives and OneNote hooks
are included. Existing page validation, project-writer/cooling protections and
semantic categories continue to apply; Notes can remain in Activity.

Offline tests use synthetic Graph responses and fake model callbacks. They cover
scope rejection, refresh/retry failures, full rereads, unchanged repeats, source
progress on model failure and pinned Reader/audit evidence. They do not establish
live Microsoft compatibility, real model quality or actual timer execution.
The acceptance record and PR distinguish those remaining gates explicitly.
