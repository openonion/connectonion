# The request returned 200. The inbox was empty.

The first WhatsApp path had a comforting shape: verify Meta's signature, parse a
message, hand it toward the client, and return success. Then we wrote the failure
fixture. It let the webhook finish and made the local mailbox raise `OSError`, as
if its disk were full.

The HTTP request had already succeeded. Meta would not retry. The inbox was
empty. Every component could log “success” while the user's message no longer
existed anywhere we controlled.

The fixture forced us to name two events that the first design had collapsed.
Meta delivering a webhook is one event. The local agent durably storing a
seven-field mailbox record is another. There can be minutes, a network failure,
or a dead laptop between them.

So the webhook stopped trying to be the mailbox. O API now verifies the raw-body
signature and WABA mapping, deduplicates the provider message id, and stores the
normalized event. A local listener claims that event under a lease. In the test,
the call order is visible: claim, local write, ACK. When the fake disk fails, the
last call is NACK instead. If the process disappears entirely, the lease expires
and makes the event claimable again.

That repair created a credential question. Moving all WhatsApp traffic through O
API would have solved routing neatly, but it would also have put the user's Cloud
API access token in a service that does not need it. The final boundary is
asymmetric on purpose: O API holds only the encrypted webhook app secret and a
hash of the verify token; outbound replies go directly from the user's machine to
Meta.

The lesson from the empty-inbox fixture was simple: an accepted webhook is a
receipt, not delivery. Delivery finishes only when the durable consumer says it
does. That is why the ACK sits after the filesystem write, even though moving it
one line earlier would make the happy path look cleaner.

A real WABA subscription is still required before the preview label can be
removed. The fixture proves what happens at a failed local write; it cannot prove
Meta app review or account permissions.
