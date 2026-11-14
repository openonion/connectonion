# Granola meeting summaries

Use `co granola --help`, then each command's help for actual syntax and recovery.
For native automatic intake, save the API key using the local hidden encrypted
input (`co env set GRANOLA_API_KEY --secret --prompt`), then follow
[native connection](granola-native-connection.md). One-off commands may still use
a temporary process key. Keep keys out of scope files, command arguments and logs.
Select one personal folder, then discover note IDs with notes. Import only the
requested scope. A child folder ID can be selected directly; `--include-children`
explicitly includes personal descendants and refuses shared or unknown spaces.

Imports are read-only for Granola and store summaries/meeting metadata locally.
No transcript, private-note body, audio or attachments are imported. A profile is
a user-chosen label, not verified remote account identity; separate keys need
separate labels and outputs. The existing personal-folder marker remains the
client implementation's explicit `space_id: null` rule, including every selected descendant.

Daily imports append changed snapshots, including same-timestamp edits, and skip
identical snapshots across stored dates. Existing shared record and immutable
reference formats remain unchanged. Collection happens outside the writer lock;
source identity and all stored daily envelopes are rechecked under the existing
REM lock. Invalid/foreign files are preserved and rejected. Records commit before
atomic source metadata; repeat the same daily scope after an interruption.

`--export ID` creates an immutable snapshot with manifest. Use a fresh ID on retry.
Exit 0 means the requested bounded read completed, not necessarily the whole
folder. Exit 1 includes auth, storage, partial and mapping failures; parser errors
exit 2. Inspect complete/rejected/mapped/appended together. Empty/all-rejected
reads create no import files. Completed details survive later transient failures
without being fetched again. Long Retry-After values stop with wait guidance
instead of blocking indefinitely or retrying early. A fully skipped daily read
may report jsonl=null because no new daily file was written.

Standalone imports do not register automatic collection. Native connections use
normal REM init/sync and its existing upkeep; opening Reader never collects.
Process evidence through the existing REM workflow;
derived knowledge belongs in existing semantic categories, never a new source
category. End-to-end REM/Reader acceptance remains separate.

See [remediation evidence](../acceptance/granola-cli-remediation.md).
API access reference: [Granola official documentation](https://docs.granola.ai/help-center/sharing/integrations/granola-api).
