# DD-068: Gmail mailbox pages and incoming downloads

Date: 2026-09-07. Status: implementation candidate. Related: #1446, #1451.

Gmail's CLI exposes its existing reversible actions and the missing inverses:
mark read/unread, archive, star/unstar, label list/add/remove. Mutations require
gmail.modify or the full-mail grant when metadata is known; missing metadata
lets the provider decide. Read and incoming downloads preserve labels.

Schema 1 JSON carries provider, account, operation, status, complete, data,
error and next_command. One invocation fetches one provider page. Message and
draft limits are 1–500; unanswered scans 1–100 candidate threads and can return
fewer matches. Estimates are labeled; filtered unanswered estimates count
candidate threads. Continuation cursors expire after 15 minutes and bind the
account digest, operation family, query/filters and limit. They are context
checks, not authorization tokens or immutable mailbox snapshots. Repeating a
page against a changing mailbox can omit or repeat rows. Listing row tokens
retain DD-067's separate immutable-ID semantics.

Unanswered means the latest non-draft message is incoming and within the chosen
window. Sort by provider internalDate, compare a parsed normalized exact mailbox,
and treat Gmail's SENT label as own-send evidence for aliases. Do not infer
aliases from other correspondents. Include threads the user started and support,
billing or invoice senders. Optional automated filtering uses Auto-Submitted or
Precedence headers; it is visible in output and never enabled by default.

Incoming attachment traversal includes named and explicitly attached/inline
parts, recursively, including attached-message children returned by Gmail.
An attached message with encoded content is one downloadable object; this
client does not parse its bytes into a second independent tree. IDs are provider
attachment IDs or part:<partId> for inline data, with structural path fallback.
Duplicate IDs fail. Limits: 1,000 MIME nodes, depth 30, 100 attachments, 25 MB
decoded per file, 100 MB decoded per invocation, and 40 MB per HTTP JSON response.
HTTP reads stream with timeouts and a byte cap; redirects are rejected. Base64
and provider length evidence must agree before publication.

Downloads require an existing directory. Strip both path separator forms and
unsafe/reserved filename characters. Existing names, including symlinks, gain
numeric suffixes. Write a private temporary file, fsync it, then atomically
hard-link to an unused destination; never replace an existing entry. Platforms
without hard-link support report failure rather than silently weakening the
contract. On platforms with directory descriptors, publication stays relative
to the opened destination directory. Successful files remain when another file
fails, with per-file status/hash/error and exit 1 for partial completion.

No label creation, automatic reply, attachment overwrite, Drive sharing or
scheduled sending is added. Draft content-bound review remains #1424.

Provider contracts: [message pages](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list),
[thread pages](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/list),
and [attachment bodies](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages.attachments/get).
