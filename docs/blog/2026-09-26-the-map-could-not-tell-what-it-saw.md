# The map could not tell what it saw

The first run looked reassuring: 13 people, 19 organizations, five projects, no errors. Then came the obvious question: how many emails had it actually read? The map could name correspondents but could not answer that. It had kept their aggregate counts and thrown away the listing that produced them.

Following the scanner exposed a worse ambiguity. It asked each mailbox for up to 200 messages per seven-day window and advanced to the next window whether it received 12 or 200. At exactly 200, Gmail might have returned the newest messages and Outlook the oldest. The output did not say which messages were missing. Calling that a map of the user's mail made a partial view look complete.

Another importer already knew how to deal with this: split a full window and ask again until each smaller interval fits. The initializer now uses that behavior for its initial 90-day scan. It writes down the source pointers it saw in private state and reports each window as it finishes. If an interval cannot be fully enumerated, the provider error leaves the map partial rather than silently erasing the gap.

The distinction matters beyond this first run. A map is a claim about coverage, not just a list of pages. The pages can stay simple; the evidence underneath must say what was observed, where it came from, and when the scan stopped. Later investigation can work from that record without mistaking a tidy first screen for a complete memory.
