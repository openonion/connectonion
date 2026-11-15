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

The author reports the targeted synthetic-vault tests passed. The live walkthrough
also verified incremental collection and exact old/new citation contexts. Broader
regression failures and the shared investigation runner's independent retrieval
remain documented limitations. This is an initial implementation for discussion
in #3040, not an approved API or a completed migration of all sources.
