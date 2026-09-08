# DD-067: Gmail rows identify one frozen listing

Date: 2026-09-07. Status: implemented on the 1.8.4 branch; acceptance in progress.
Related: #1446, #1424, #1450.

`sent` printed row numbers while `read` resolved a previous inbox/search cache.
A mutable account-scoped cache would fix that case but still let two terminals
change what the same number means. Every Gmail message and draft listing now
gets an immutable random token. A numeric reference requires `--listing TOKEN`;
tips use full provider IDs. Full IDs skip listing reads and profile lookup.

Schema 1 stores provider, SHA-256 of the normalized provider-confirmed mailbox,
message/draft family, token, creation/expiry times, and ordered full IDs. The
global config directory retains up to 128 ID-only files, created exclusively
with mode 0600, each valid for 15 minutes. No subject, recipient, body or token
credential is cached. Invalid, corrupt, stale, evicted or account-mismatched
references fail closed with a relisting hint. Legacy mutable caches are ignored.
Other listings, including empty results, cannot retarget earlier tokens.

This intentionally changes bare-number behavior. A saved email field cannot
establish account identity because it may be stale; Gmail's profile endpoint
provides the account. Resolving a missing row by fetching a new inbox would
hide caller context loss, so that fallback is removed. Sent uses the same
structured listing and rendering path as search and inbox.

`read --mark-read` remains opt-in. A known insufficient grant exits 1; absent
scope metadata lets the API decide. Printing the body does not make a failed
requested mutation successful. Mailbox expansion and draft-send payload safety
remain separate dependent changes.
