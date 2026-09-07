# DD-066: One selected env and whole provider records

Date: 2026-09-07. Status: implemented on the 1.8.4 branch; acceptance in progress.
Related: #1444, #1313, #1445. Supersedes the env-loading policy in #1381/#1382.

The owner confirmed that global configuration and identity are the defaults for
all settings. Working-directory discovery cannot select a project dotenv file.
Use one root CLI option, `--env-file PATH`, and retain the existing `keys.env`
store. The full precedence, persistence and migration contract is in
[Environment selection](../cli/environment.md).

Provider clients bind one record at construction. Ordinary process settings win
per key; Google/Microsoft process credentials win as whole records and refresh
in memory. File credentials use the selected path for both consent and refresh.
Refresh preserves omitted metadata, validates response types and expiry before
writing, and locks the read/network/write sequence. Atomic replacement prevents
partial reads. A changed account is an actionable conflict, not a new consent
request. Missing scope metadata does not prove a provider permission denial.

Rejected alternatives: switching loader order only in Outlook leaves package
startup and other clients inconsistent; per-field fallback combines accounts;
writing every known `.env` propagates stale accounts and credentials; copying
project data to a new global store creates a second source of truth; a hash check
without serializing refresh still races token rotation.

Partial records without provable continuity can require retrying with a newly
resolved client after another writer changes them. This is preferable to
overwriting an account we cannot identify. Process overrides require caller-owned
durability; they do not implicitly authorize replacing the global record.
