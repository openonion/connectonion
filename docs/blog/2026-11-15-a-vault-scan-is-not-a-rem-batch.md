# A vault scan is not a REM batch

Local design draft: the single-vault provider now exercises the proposed shared dispatch.

The single-vault prototype already had a function called `collect`: it walked
the selected folders and saved changed note versions. The proposed shared
source interface also had a `collect` function, but that one meant something
different: read a bounded batch from material already saved.

Connecting the names directly would make a supposedly offline REM batch scan
the live vault again. The adapter instead places acquisition behind `fetch`.
Batch collection reads the saved change log and returns a proposed cursor;
the caller commits that cursor only when it accepts the work.

There was another boundary to settle. A note may change several times before
REM consumes it, or disappear while it is waiting. Replaying every queued
body would present old content as new evidence. The batch reader therefore
offers current versions and skips obsolete events. A page's historical
citation can still retrieve the exact saved version it originally used.

Static review caught a consequence of limiting the history scan to one page:
a page full of obsolete events could produce an empty batch even though a
current note remained later in the log. The local implementation now streams
past skipped history until it reaches eligible content or the end. Output
still has item and character limits; scanning a long history can take time.

The integration now registers the module once and routes public sync, investigation
and reader citations through selected-source hooks. It reuses #3055's version
identity functions, while routing registered versions by notebook selection rather
than importing every provider at startup. Existing kinds are not all migrated yet.

A second lesson emerged at the lock boundary. Offline reads can happen inside a
stage transaction, so taking the ordinary maintenance lock again would deadlock or
fail. A dedicated material-read context reuses only a lock owned by the same process,
thread and notebook. Ordinary writer locks retain their non-reentrant behavior.

Approval must also survive waiting and retries. The store rechecks the scope and
receipt after obtaining its lock, and every actual model attempt rechecks retained
material, including timeout retries. Wrapping only the retry loop would miss a
revocation between its two attempts. Already sent requests cannot be recalled.

The 2026-11-20 alignment uses the shared hooks from #3228. A scan holds a separate
acquisition lock while reading the live vault, then takes the shared guard only
to validate and publish its result. Offline readers do not take the acquisition
lock. Holding both locks throughout a scan would make a reader inside the notebook
transaction wait on a writer that itself needed that transaction to finish.

Filesystem identity needs the same care as saved configuration. A folder can be
replaced with a symlink without changing subscriptions. Resolving the saved vault
again and accepting the new destination would silently change the authorized
scope. The adapter now checks the saved canonical paths, reads through that
validated scope and checks it again after scanning. Scope errors block saved
material until successful reacquisition; a temporarily unavailable folder can
instead retain explicitly stale, approved snapshots.

The local candidate passed focused synthetic-vault and affected REM regression
tests; [the validation record](../rem/obsidian-validation.md) separates these from
the earlier live walkthrough and its historical failures. The runner's independent
retrieval remains a documented limitation. This is a source-specific migration
for shared-PR review, not a completed migration of all sources.
