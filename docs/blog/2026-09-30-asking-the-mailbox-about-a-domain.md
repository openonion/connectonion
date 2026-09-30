# Asking the mailbox about a domain

The 1.9.0a1 acceptance run investigated the UNSW page on a copy of the owner's
real notebook. It took 18.5 minutes. About 10 of them went to listing every
mail header in the window, week by week: 2,269 from Outlook and 1,557 from
Gmail, each one read only to check whether `unsw.edu.au` appeared in it.

People had stopped doing this some time ago. A person arrives with an address,
and both mailboxes answer "every mail this address is on" directly, in about a
second. An organisation arrives with a domain instead, and the code only knew
how to search the server for handles with an `@` in the middle. A bare
`unsw.edu.au` fell through to the fallback: list everything, filter locally.

The turn was realising the servers had never needed the `@`. Gmail's `from:`,
`to:` and `cc:` accept `unsw.edu.au` the same way they accept an address, and so
does the `participants:` term the Outlook client sends. The slow path was not
a limit of the mailbox. It was the code refusing to ask a question the mailbox
could already answer.

So an org page with a domain handle now makes one server query per domain
instead of walking the window. The server may match loosely; what it returns is
still checked against the page's handles before anything is read. The rule
applies to org pages only, because a person's alias like `vern.chan` has the
same shape as a domain and is not one.

The lesson is to look at which question the slow path is answering. Listing
3,826 headers was answering "what mail exists?", when the page only ever asked
"what mail involves UNSW?". The second question has a direct answer, and we had
been answering the first one to get it.

What has not been done yet is running this against a real mailbox. The tests
use fake clients that record the queries they receive. Whether Outlook's
`participants:` matches a bare domain as well as Gmail's operators do is the
first thing the next acceptance run on the owner's notebook will check.
