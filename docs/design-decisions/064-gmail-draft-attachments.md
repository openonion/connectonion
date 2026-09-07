# 064 — Gmail draft attachments are provider-native and review-gated

## Status

Accepted for ConnectOnion 1.8.2.

## Problem

`co gmail send --attach` sends immediately. That is useful for automation but
is a poor interaction for assembling a message from several local and Drive
files: a person cannot inspect the final manifest, correct one attachment, or
abort after seeing the composed result.

## Decision

Expose a visible nested `co gmail draft` group with seven verbs: `list`,
`create`, `attach`, `remove`, `replace`, `preview`, and `send`.

Gmail's provider draft is the source of truth. The implementation reads its raw
RFC 5322 message, edits MIME parts, and replaces the draft through Gmail's
draft-update endpoint. It does not keep a second local draft manifest that can
drift from Gmail. The Gmail draft ID remains stable across updates.

Local files use the existing regular-file, symlink, and 25 MB attachment
guards. A Drive file is downloaded or exported into bounded memory and inserted
directly into the MIME draft; no temporary copy is written and the Drive item
is not changed. `--drive --link` appends the file's web URL and explicitly does
not modify Drive sharing.

Only `co gmail draft send` sends. It prints recipients, body, and the final
attachment manifest, then asks for confirmation with a default of no. It has no
non-interactive bypass. Declining leaves the Gmail draft intact. Draft sending
is private in the Python tool so an agent cannot bypass the CLI's review gate.

## CLI contract review

The project CLI design guide led to these interface choices:

- the workflow is discoverable in `co gmail --help` rather than hidden in flags;
- the CLI routing table and matching `co-mail-and-drive` skill name the same
  seven commands;
- every successful or guarded-failure path prints a literal next command, and
  that tip remains in non-terminal output;
- numbers resolve only through the last matching listing cache, while a full
  provider ID remains valid;
- guarded failures exit `1`; Typer syntax failures exit `2`;
- send confirmation cannot be bypassed by a convenience flag.

## Alternatives rejected

- **Only add more flags to immediate `gmail send`.** This leaves no stable
  object to preview or correct before delivery.
- **Keep the draft manifest locally.** Two sources of truth can disagree after
  Gmail web or another client edits the draft.
- **Download Drive files to a temporary path.** The CLI needs bytes, not a
  user-visible copy; bounded in-memory transfer reduces residue.
- **Offer `draft send --yes`.** That would turn the review gate into an optional
  convention and make accidental agent-driven delivery easier.

## API contract

This design uses Gmail `users.drafts.list`, `get`, `create`, `update`, and
`send`, plus Drive `files.get` media downloads or `files.export` for supported
Google-native documents. Gmail draft updates replace the whole message, so
each edit starts from the latest provider copy.

References:

- <https://developers.google.com/workspace/gmail/api/guides/drafts>
- <https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts>
- <https://developers.google.com/workspace/drive/api/guides/manage-downloads>

## Security and operational limits

The CLI reuses the standard Google session and never prints token values or raw
provider error bodies. Gmail draft writes require a token with `gmail.modify`,
`gmail.compose`, or full Gmail scope. The shipped OAuth flow grants
`gmail.modify`. Drive links can still fail for recipients who lack access;
users must change sharing themselves or attach the bytes instead.
