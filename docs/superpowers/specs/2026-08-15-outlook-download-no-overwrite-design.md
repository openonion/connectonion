# Outlook Attachment Downloads Must Not Overwrite Existing Files

## Goal

Fix Issue #923 so `download_attachments()` never loses an attachment or clobbers an existing local file when attachment names collide.

## Design

Keep the current sender-controlled filename sanitisation and destination-directory boundary checks. After sanitising each attachment name, select the first unused path: the original filename, then `stem-1.suffix`, `stem-2.suffix`, and so on. This preserves the original name whenever possible and keeps extensions intact.

The method continues returning the paths actually written, so the CLI's existing output reports the disambiguated filenames without an interface change. The selection and write happen in the same method, using the existing local filesystem behavior; no dependencies or public API changes are needed.

## Verification

Add unit tests proving that two attachments with the same name produce two files with both payloads preserved, and that an existing destination file is preserved while the attachment is written to a suffixed path. Run the focused Outlook unit tests and the repository's non-real-API test suite.

## Scope

Only `connectonion/useful_tools/outlook.py`, its Outlook unit tests, and a required `docs/blog/` design journal entry are changed. No unrelated refactoring or documentation restructuring is included.
