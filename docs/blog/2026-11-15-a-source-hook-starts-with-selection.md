# A source hook starts with selection

Design journal draft, updated 2026-11-20. This shared prerequisite is based on
#3055 and the three-team discussion in #3040. It has not shipped. The author-run
offline checks below cover local candidates, not a published release.

Three sources enter REM at the same places: acquisition, batch reading,
investigation and citations. Repeating a provider branch at each place makes
source authors edit the same generic files. Discovering every provider before
choosing one can also decrypt a token or scan a vault for an unrelated notebook.

The boundary starts with saved selections. Registration stores a module path,
while passive metadata display uses saved names and scope without loading it.
The explicit configuration action loads only the requested configuration module.
Content operations require the current scope and model approval. This is a
contract for trusted Python adapters, not an isolation sandbox.

Acquisition and consumption have different lifetimes. Fetch saves snapshots
outside the long-lived notebook lock; publication uses a short approval guard.
Offline hooks read atomic committed state without waiting on the writer lock.
That last constraint matters: a writer holding its storage lock while waiting
for the notebook would deadlock with a notebook reader waiting on that writer.
A batch proposes consumption progress; existing accepted-work paths publish it.
A failed turn can read the same batch again.

Granola exposed a second distinction. Its record identity is source-qualified,
but the Reader target starts with `adapter:` and contains a file, record ID and
content hash. Rewriting that target to select a provider would also change a
working citation format. The shared layer instead retains its bytes and persists
validated owner metadata. Ownership survives restart, while current approval
still gates every lookup and retained model turn. A missing adapter cannot turn
saved private evidence into uncontrolled input.

We considered putting all three adapters into the same change. The teams agreed
on a shared prerequisite followed by source-owned migration PRs instead. This
candidate wires generic callers using synthetic providers; it contains no real
SDK, credential handler or production source registration. That keeps interface
review separate from account and storage behavior, but requires each team to prove
its actual port. Synthetic compatibility is not evidence of a real-service run.

Other concrete choices remain reviewable: explicit configuration before consent,
strict serialized-character budgets, first-item clipping, temporary stale fallback
and the ownership metadata schema. Unexpected errors still propagate; integrity
and account failures block retained reads until a successful acquisition.

The local adapter run exposed an additional concurrency mistake: a second Obsidian
collector failed immediately when the first held its acquisition lock. Bounded
waiting outside the notebook lock let both collectors finish without saving duplicate
versions. A test now forces that contention while an offline reader checks committed
state. Before integrating newer main, the shared suite passed 73 focused cases and 1269 caller regressions; the
separate adapter suite passed 1337 focused cases and 1269 caller regressions. Both
passed the five requested CLI audits. Real service access and existing-store
migration still need evidence from each source owner.

The local merge with main `fe50d346` is uncommitted. It combines append claim
retention with version-aware source checks,
extends native acquisition to catchup and collection-only paths, and recognizes
registered and opaque targets in topic mapping. A snapshot path's embedded date
must not become the date of a claim. Source acquisition uses main's deadline and
repeated-stall protection without holding the long notebook lock. The earlier
passing results do not cover this merged candidate. A new author-run check of
the merged candidate passed 103 focused cases and 2104 caller regressions. Three
source audits passed; the script then stopped on the compatibility-only `sync`
target, which main no longer lists in its public help tree. The corrected script
uses `collect` instead. The author's follow-up `collect` and `start` audits both
passed, completing the five planned public-command audits for this candidate.

A later static review found cases that those tests had not covered. Overlapping
acquisitions could publish an old success after a new account failure. The local
fix preserves a changed blocking receipt and requires a fresh retry, rather than
holding the notebook lock during network work. Approval also needs to bind every
effective model route, not only the default model. Per-source approval records now
survive automatic mailbox grants without being renewed by them, and confirmation
checks the displayed snapshot before publishing consent. Prepared tasks keep their
execution snapshot so a newly approved model cannot legitimize a cached old one.
The author then ran the updated checks: 136 focused cases and 2238 caller
regressions passed, together with all five public-command audits. Both pytest
runs reported the real `~/.co` unchanged. These are local synthetic and caller
results; real-provider migration and source-team review remain separate work.

See the [interface overview](../rem/source-interface.md),
[contract](../rem/source-interface-contract.md) and
[validation record](../rem/source-interface-validation.md).
