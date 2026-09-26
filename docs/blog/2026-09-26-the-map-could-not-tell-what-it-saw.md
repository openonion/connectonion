# The map could not tell what it saw

The first run looked reassuring: 13 people, 19 organizations, five projects, no errors. Then came the obvious question: how many emails had it actually read? The map could name correspondents but could not answer that. It had kept their aggregate counts and thrown away the listing that produced them.

Following the scanner exposed a worse ambiguity. It asked each mailbox for up to 200 messages per seven-day window and advanced to the next window whether it received 12 or 200. At exactly 200, Gmail might have returned the newest messages and Outlook the oldest. The output did not say which messages were missing. Calling that a map of the user's mail made a partial view look complete.

Another importer already knew how to deal with this: split a full window and ask again until each smaller interval fits. The initializer now uses that behavior for its initial 90-day scan. But the owner noticed a second waste: even after finding a person, investigation would ask the mailbox to list that person's mail again. The first pass had found the material and then let it go.

So the first pass keeps a private copy of each provider-rendered body, with a reference file for each mapped person. A message to two people remains one body with two references. Project files similarly point to the sessions already on disk. Investigation reads the local material first and asks the provider only about time outside the saved range. The map still appears before the body download finishes; a failed download leaves an explicit partial status and can be resumed.

This costs more time and disk during the first run, and the body snapshots are sensitive enough to stay outside shareable Wiki pages. That is the trade: a map is a claim about coverage, not just a list of pages. The evidence underneath must say what was observed, what was saved, and what still needs fetching before a tidy first screen can be treated as a useful memory.
