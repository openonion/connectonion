# The Gap After Review

Draft for 1.8.4; publish after release acceptance.

The draft send handler looked careful. It fetched a Gmail draft, printed its
recipients and attachments, then asked for confirmation. After the operator
answered, it called Gmail with the draft ID. The ID was the problem: it named
an editable object, not the message the operator had just read.

The first repair seemed straightforward. Fetch the draft again after
confirmation and compare a content hash. That catches an edit made while the
prompt is open. It still leaves an interval between the comparison and the
send request, when another Gmail client can replace the content behind the ID.
Adding another comparison only moves the interval.

Google's draft guide supplied the useful distinction. The send request can
include an updated raw message alongside the draft ID. We can compare the
review and submit the reviewed bytes in that same request. The regression now
edits the simulated provider draft during the final permission check. The send
payload still contains the original reviewed body. The late edit cannot become
the outgoing message.

This choice has a cost we need to state. Gmail consumes the draft when it sends.
A concurrent edit may be discarded. The implementation protects which bytes
leave the account; it cannot promise to preserve another client's simultaneous
work on an object that the provider removes.

Then the test lost the send response. Retrying the command would be tempting:
there is no receipt on screen, and the draft might still appear briefly. But a
timeout says nothing about whether Gmail delivered the message. The client now
writes an attempt record before submission and gives the outgoing message a
stable Message-ID. A repeated command looks for that message in sent mail. One
match recovers a receipt; no match leaves the outcome uncertain and does not
send again. The record contains hashes and IDs, not the message body.

Working through attachment review exposed a related identity problem. A managed
Drive link has to survive a new CLI process, but an arbitrary URL in the body
must not become an attachment merely because it looks like Drive. The draft
therefore carries explicit source records inside its MIME. A reload test passed,
then a CRLF round-trip test failed because provider line endings changed the
stored link's text comparison. Normalizing that comparison preserved the record
without adopting unrelated URLs. The send path removes internal source headers
after including them in the review.

Review now identifies content at the point where the operator can inspect it,
and the final request carries that content across the boundary. The remaining
live test has to prove Google preserves those records and delivers the declared
exports. Mocked races establish the client behavior; they do not stand in for
that provider acceptance.
