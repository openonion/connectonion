# DD-069: Reviewed draft bytes and provider-backed source records

Date: 2026-09-07. Status: implementation candidate. Related: #1424, #1444, #1446.

`draft review [--json]` is the canonical pre-send review. Existing preview stays
available for inspection. No redundant show/attachments/attach-drive leaves are
introduced. Attach uses `--drive [--link]`; replace adds the same link option.

A review hashes account, draft ID, thread ID and SMTP-serialized provider MIME.
It includes all recipients, From, body/digest, source items, file totals, final
MIME/base64 sizes and warnings. A caller supplies the token to send or uses a
real terminal's default-No prompt. Piped input cannot approve. Send re-fetches
and rejects changed content, then sends those frozen bytes and draft ID in one
provider request. Gmail's [draft guide](https://developers.google.com/workspace/gmail/api/guides/drafts)
explicitly supports this payload. Re-fetch followed by ID-only send was rejected
because another client can edit the draft between those operations. Gmail has
no edit compare-and-swap: consuming a draft can discard a concurrent late edit,
but that edit cannot replace the outbound bytes.

Before submission, a locked, private global send ledger records an account/draft
hash, review hash and deterministic RFC Message-ID. It never stores draft bytes
or recipients. A successful receipt is persisted. An ambiguous response leaves
the submitted marker; subsequent calls search sent mail for that Message-ID and
return one matching receipt or remain uncertain without resending. Explicit HTTP
4xx rejection (except request timeout) permits a deliberate new attempt. This
is local retry safety, not a provider exactly-once claim across machines or
unrelated clients. Records are not automatically expired or deleted: silently
forgetting an uncertain send would re-enable duplication. Inspect before any
manual recovery, and preserve the ledger with the global configuration.

Private source headers contain explicit local/Drive byte provenance and hashes.
Managed Drive links have structured records on the root MIME message and exact
plain-text body lines. Records survive provider reloads, including CRLF line
endings. Independent managed-text changes fail review until removed/replaced;
ordinary body URLs never acquire managed status. Review shows records, then
strips those internal headers from the outgoing MIME. File-only attachments
remain compatible; the additive items manifest lists files then links. Numbers
refer to the current draft manifest, so inspect it after edits. Source records
are descriptive provenance, not a provider-signed attestation.

Replacement builds and validates one new MIME message before one update. A
preflight failure leaves the provider untouched; a lost update response still
requires inspection. Preserve the existing 25,000,000-byte decoded file limit
and enforce a 35,000,000-byte final MIME cap. Drive export streams use the current
remaining file budget, then the update validates again against the latest draft.
Metadata inspection returns unknown sizes as null, resolves at most 20 shortcut
entries, rejects cycles/trash and never grants recipient access. Native exports
remain Markdown/CSV/PDF as documented by the existing Drive adapter.

Drive now shares the immutable listing mechanism with Gmail, using a distinct
provider/files context. Get/info/rm numbers require --listing; Gmail's Drive
source numbers require --drive-listing, independent of its draft --listing.
Full IDs work throughout. Tokens expire after 15 minutes, retain at most 128
lists and store IDs plus account hashes only. Legacy last-listing files are
ignored. Both provider clients confirm the same Google account before crossing
from Drive into Gmail. This migration prevents another process or account from
retargeting a previously displayed Drive row.

The existing Google local credential/refresh contract remains authoritative.
No broker content endpoint or new OAuth scope is introduced. Google accepts
compose/modify/full-mail grants for draft operations; unknown local grants let
the provider decide. No agent-callable draft send or approval bypass is added.
