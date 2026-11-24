---
description: An inbox could return the sentence that referred to a purchase order while losing the purchase order itself. Following the bytes changed the receiver, the API and the CLI together.
tags: [Email, Attachments, Reliability]
---

# The email that lost its PDF

The first question was whether an emailed PDF would be on the agent's server.
The inbox command could show a sender, subject and body. That made receiving an
email look like a finished operation. A purchase order attached to that email
was a separate question.

Following the message backwards exposed two losses. The Cloudflare receiver
parsed MIME and forwarded the text and HTML bodies. It did not forward the
files. The mailbox backend stored those bodies. By the time the Python tool
returned a dictionary to the agent, there were no PDF bytes left to ask for.
Adding a PDF reader to the agent would have changed none of that.

The receiver now forwards the original MIME bytes, encoded for the signed
webhook. The mailbox backend stores the original message and its decoded files
in one database transaction. The agent's VM downloads a copy when it needs one.
That distinction answers the original storage question: a received file belongs
to the mailbox first; it does not appear on every machine that can read the
mailbox.

One failed file insert was a useful test. If the body survived while the file
did not, the system could again present an email as complete. The PostgreSQL
test makes the second file fail and checks that neither the email nor either
file remains. A concurrent replay checks the other direction: receiving the
same original message twice must leave one email with one set of files.

Sending needed the same attention. A retry with the same subject and body but
a changed PDF is a different request. Attachment names, types and checksums now
participate in the send identity, and the original bytes are retained with the
send reservation. The database tests also cover a rejected send being retried:
its files must not be inserted twice or consume another allowance unit.

The CLI has explicit commands for listing files, downloading them and reading
their text. Downloads verify size and SHA256 and refuse to overwrite an existing
file. A new client uses a dedicated attachment-send endpoint, so an old server
fails visibly instead of accepting a message while ignoring its files.

Keeping the PDF and reading it remain separate outcomes. A scanned page can be
stored and downloaded exactly while containing no extractable text. The reader
reports that it needs OCR or review. An empty extraction is no longer a reason
to pretend that a purchase order had no lines.

These changes have focused command and API tests, plus real PostgreSQL tests
for retention, rollback, mailbox permissions and retries. Publication still
follows the framework's normal release process. The final rollout check is a
message that crosses real SMTP and Cloudflare, followed by a byte-for-byte
attachment download; a successful local webhook alone cannot establish that.
