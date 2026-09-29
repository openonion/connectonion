# Asking the mailbox about a domain

The 1.9.0a1 acceptance run investigated the UNSW page on a copy of the owner's
real notebook. It took 18.5 minutes. About 10 of them went to listing every
mail header in the window, week by week: 2,269 from Outlook and 1,557 from
Gmail, each one read only to check whether `unsw.edu.au` appeared in it.

People had stopped doing this some time ago. A person arrives with an address,
and both mailboxes answer "every mail this address is on" directly, in about a
second. An organisation arrives with a domain instead, and the code only knew
how to search the server for handles that contained an `@` in the middle. A
bare `unsw.edu.au` fell through to the fallback that lists everything and
filters it locally.

The fix is less than it sounds, because the servers already take a domain
where they take an address. Gmail's `from:`, `to:` and `cc:` accept
`unsw.edu.au`, and so does the `participants:` term the Outlook client sends to
Graph. So an org page with a domain handle now makes one server query per
domain instead of walking the window. The server is allowed to match loosely;
what it returns is still checked against the page's handles before anything is
read. The domain rule applies to org pages only, because a person's alias like
`vern.chan` has the same shape as a domain and is not one.

The same run's coverage line said "0 loaded from private init archive". Init
had already saved 90 days of mail bodies locally, and a person's page reads
them through an index built at init. Orgs never got an index. They do not need
one: each saved snapshot carries its own from, to and cc, so reading the
snapshots and keeping the ones a domain is on is the index. When the archive is
complete, an org now reads from it the way a person does, and the server is
asked only about the days the archive does not cover.

The third thing the run showed was smaller and more irritating. Session
gathering printed "gathering claude-code sessions" up to 24 times, identically.
The CLI prints a count only beside a total, and sessions have no total, so the
count that was passed never appeared. The count now goes into the line itself
("gathering claude-code sessions: 1,200 scanned"), and a batch that added
nothing prints nothing.

What this change has not done is run against a real mailbox. The tests use
fake clients that record the queries they receive. Whether Graph's
`participants:` matches a bare domain as well as Gmail's operators do is the
first thing the next acceptance run on the owner's notebook should check.
