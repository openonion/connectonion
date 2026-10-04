# The mailbox that was there

The first lifetime REM estimate found people in Outlook and none in Gmail. The
Gmail account was connected, but the request for its own address waited thirty
seconds and timed out three times. That is a dangerous kind of empty result:
the notebook can look orderly while an entire part of the owner's history is
missing. REM marked its estimate as a lower bound, which made the absence
visible, but it still could not answer the owner's question about all people.

The same credential could read Gmail's profile and send-as aliases through the
CLI's bounded direct request in about a second each. A one-day listing and a
message header worked too. That pointed to the SDK transport used by REM, not
to a disconnected account. We moved this metadata path to the direct reader.
The first live one-day probe then saw ten messages in 6.19 seconds without
opening their bodies.

History changes the cost of a small implementation detail. REM splits a window
that reaches the provider's 200-message cap, so it must avoid fetching headers
for a window it will throw away. In the smaller windows it now reads up to
eight headers at once. The listing authenticates the bound account before
workers start; each worker reuses that token instead of building a separate
Google service and refreshing it. A failed header stops the window rather than
turning nine successful reads into a claim of ten.

This repairs the doorway, not the full walk. The lifetime metadata scan is
still being measured. Rate limits, a stopped run, and the quality of hundreds
of written memories each need their own evidence before the product can call
this a complete understanding of the owner's people.
