# An empty map needs an explanation

The user ran Wiki initialization, opened the reader, and found no people. They had already connected their mailbox. From their side, the work was done: there was an account, a command, and a page that ought to show the result.

The command had returned successfully. Inside the program, that meant the selected sources had been processed. Mail was disabled by default, so there was no selected mailbox to process. The program had respected a boundary the page never explained.

Our first correction made that boundary visible. Initialization would offer a connected mailbox, and a script could select one explicitly. A live run over thirty days of Outlook metadata produced 158 entries. We could have stopped there: the empty page had filled up.

Then we made the mailbox fail. The people list was empty again, but the command still returned success. The report contained an unavailable-source message farther down; its headline said the map was complete. We had repaired the happy path while leaving the original ambiguity intact. A person could not tell whether nobody had been found, nobody had been searched for, or the search had failed.

That changed what we considered the result of initialization. A map is accompanied by an account of its coverage. If a selected mailbox cannot be read, initialization now reports a partial failure and keeps whatever other maps it completed. If no mailbox was selected, it explains the choice and gives a command that targets the same notebook. Neither condition earns a claim that the requested work is complete.

The remaining limit matters too: a mapped correspondent is not an investigated person. Finding an address tells us where to begin. The lesson from the empty page was to make those boundaries visible before making the page look reassuring.
