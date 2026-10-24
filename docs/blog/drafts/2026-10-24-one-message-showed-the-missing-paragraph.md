---
title: One test message showed the missing paragraph
date: 2026-10-24
status: draft
description: Connecting two clients to the same mailbox exposed a transport assumption that matching IDs could not reveal.
---

The first comparison looked reassuring. A browser had connected to the same
OpenOnion account as the terminal. Inbox and Sent contained the same message
IDs. Opening a message produced the same plain text. The private key had stayed
on the computer throughout the connection.

Then we sent a message from the browser back to that account. It arrived once,
with the Chinese text intact. Its paragraphs had become a single block.

Both clients were using the same API, but the terminal had already learned
something the browser did not know: this mail service treats its body as HTML.
The CLI escapes plain text and represents paragraphs and line breaks explicitly.
The browser had handed it the textarea's raw newlines. An API can accept a value
successfully while delivering a different reading experience.

That changed the acceptance test. A matching ID established that both clients
could see the same record. It could not establish that the reader received the
message as written. The web transport now follows the CLI's paragraph convention,
and legacy HTML bodies have a readable text representation that retains URLs.
Literal angle brackets are escaped before sending; they remain the author's
words when read back.

There was a similar choice at login. Generating a new browser identity would
have produced an account without the existing mailbox. Copying a private key into
the page would have expanded what the browser held. Instead, the browser creates
a short-lived challenge and the selected local identity signs that exact request.
The resulting session belongs to the mailbox the operator already uses.

The command surface needed the same care. Reading an old sent message by scanning
the newest hundred was a window onto a mailbox, not a reliable read by ID. The
backend already offered the direct Sent read. Received mail needed the matching
permission-scoped endpoint. A bulk state change also needed to say how many
messages had changed before a later request failed.

An independent AI review caught a quieter discrepancy in an address-change
preview: an uppercase spelling of the existing name was priced as a rename,
although the server normalized it and would charge only for a domain change.
Normalizing before the preview made the displayed decision agree with the
server's decision. Those paid paths were checked with mocks, not purchases.

This is a source candidate and a running web client, not a claim that a new CLI
package has been published. Protocol, expiry, content fidelity, safe previews
and recovery have focused tests; email help is checked as an operator encounters
it. The useful evidence is still the small round trip: write a message, receive
it, and compare what survived.
