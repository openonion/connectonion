# Gmail kept the body and changed the ID

The preview sent its test email successfully. Our acceptance script still failed.
The saved provider receipt said the send had happened, but searching for the
Message-ID we had reviewed found nothing. Retrying the send would have answered
the wrong question, at the cost of another email.

We first inspected the one synthetic message already in the account. Its recipient
was correct, its replacement attachment was present, and the internal attachment
source headers had been removed. That last detail mattered: it suggested Gmail
had used the frozen outgoing message. The evidence did not support blaming the
whole raw-MIME request just because one header had changed.

A smaller experiment separated those possibilities. A short plain-text self-send
arrived in the inbox with the expected body, but Gmail replaced its Message-ID.
Shortening our identifier did not help. Using the account's domain did not help
either. The next experiment added a dedicated attempt header. Gmail preserved
that value while replacing Message-ID again.

The local send ledger was already doing its most important job. Once submission
was uncertain, it refused to send again. What had failed was our way of finding
the receipt afterward. We had treated a header we supplied as a header the
provider would necessarily preserve.

Recovery now has a second, narrower piece of evidence. The reviewed MIME carries
an attempt marker, and the private ledger records that marker with the submission
time. If the original Message-ID lookup finds nothing, recovery examines a bounded
page of recent sent-message metadata. It returns a receipt only for one exact
marker match. Another page, two matching messages or no match leaves the send
uncertain. A subject match would have been easier to implement, but it would not
identify the operation the user approved.

The live test then simulated a missing receipt after a real send, with the send
method replaced by an assertion that forbade another submission. Recovery found
the stored message. The body and attachment hashes also matched the reviewed
content. That tested the provider behavior the mock had never challenged.

The next failure was more mundane. Downloaded attachment hashes matched, but our
path assertion rejected the destination. macOS had resolved `/var` to
`/private/var`; the downloader used the resolved path and the test did not.
Comparing resolved directories fixed that assertion without relaxing the rule
that downloads must stay in the requested directory. The full live journey then
passed, including mailbox actions and two collision-safe attachment downloads.

These are local fixes after the published 1.8.4a1 preview. They do not change the
bytes already on PyPI, and they do not turn an unconfigured physical NAS into a
passed test. They do change what the next acceptance run measures: the content
Google stored, the receipt we can recover, and whether another send was prevented.

## The receipt became the release criterion

When the preview was ready for promotion, a green command was no longer enough
for us. The first test had already shown why: the provider had completed the work
while our local lookup insisted it had not. We went back to the lost-receipt case
instead of adding a retry to make the command look successful.

That distinction survived the stable review. Recovery still has to find one
provider-preserved marker within a complete bounded page; an ambiguous result
still leaves the send uncertain. Promoting the package does not widen that search
or make a subject line count as a receipt. If Gmail stops preserving the marker,
we will need another way to identify the approved operation before allowing
recovery to report success.

The 1.8.4 release includes that behavior after the real self-send journey and the
combined 8,665-test regression run. The mock remains useful for proving that an
uncertain send cannot repeat. The stored message remains necessary for proving
that our chosen identifier survives the service. Neither test can replace the
other; the first failed acceptance run is the reason we now keep both.
