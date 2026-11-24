---
description: What we learned from tracing an attachment from the Cloudflare mail Worker to the agent's inbox.
tags: [Email, CLI]
---

# The mail that left its attachment behind

When we checked whether an agent could receive a report by mail, the inbox
looked healthy. It showed the sender and subject and could print the body.
Those were also the only parts of the message the database saved. The clue
was in the parser: it walked the MIME message looking for plain text and
HTML, then gave the database two strings. By the time the CLI opened the
inbox, the report had already been dropped.

We first looked at the existing agent file transfer. It solves a different
lifetime problem. An offline agent's file can disappear once the recipient
takes it, while the attachment on an email needs to be there when someone
reopens that email a week later. We gave the attachment the same lifetime
as the mail and used the mailbox's existing read permissions for each
download.

A retry was the detail that made the shape of the fix clear. If the Worker
repeats a delivery after a timeout, the database must decide whether it
already has the original before saving its files. We ran two concurrent
deliveries against PostgreSQL and got one inbox row and one copy of each
attachment. A download returned every byte of the binary test file. A
second account received a 404 for the same download URL.

That check changed what we mean by a successful delivery: a readable
subject and body are only part of it. The report should still be there
when the agent asks for it, and only someone who can read the mail should
be able to get it.
