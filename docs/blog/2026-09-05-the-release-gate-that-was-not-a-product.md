# The Release Gate That Was Not a Product

The browser switching test had finished. On a dedicated account, the CLI closed
the free browser, opened Onion, read and changed a test page, closed it, and
returned to a working free browser. The account had spent one $0.025 interval.
Yet the release still appeared blocked: we were looking for a panel button to
repeat the same journey.

There was no such panel in this product. We had carried the word “panel” into
the acceptance criteria and then treated the missing screenshot as missing
engineering work. Searching the browser's billing page and the agent's Control
Center did not resolve it, because neither was the CLI engine selector the
test was supposed to exercise. The user corrected the scope: the product has
CLI switching, and that is the boundary to verify.

That correction did not mean accepting every green-looking result. The proxy
test had found a real failure: a rejected navigation still exited successfully.
Status had also said Chromium was missing while the browser was working. Those
needed code changes and regression tests. The absent panel needed neither.

For the 1.8.1 candidate, we kept the recorded paid lifecycle evidence and stopped
opening new billable sessions to answer the wrong question. We brought the two
diagnostic fixes onto main and used non-billing checks to verify the candidate.
The default remains the free system browser. Paying is an explicit session
choice, not an automatic switch on each read or write.

A release checklist is useful only while each item describes a promise the
product actually makes. Here, removing an invented gate let us concentrate on
the failures an agent could really encounter.
