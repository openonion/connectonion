# The upgrade that kept yesterday's mistakes

For two weeks every release of co rem made the map better. It learned that
"Airbnb" writing from airbnb.com is a service, not a person. It learned that
an address the owner writes to a hundred times and never hears back from is
probably the owner's own. It learned that a skill installed in three folders is
one skill. Each fix had a test, and each test passed on a fresh notebook.

Then the owner ran 1.9.0a5 on the notebook he actually uses, and it still had
all of it. GitHub's `unsub+…@reply.github.com` addresses as people. Apple ID.
`notify@x.com`. Two of his own addresses waiting in the queue to be
investigated as strangers. Three pairs of pages for one skill. The reader said
"174 with findings" when three pages had been written. Every rule was right,
and none of them had ever looked at a page that already existed.

That was the turn: a better map changes what the next map makes, not what is
already on disk. The fixes needed a second half that reads the old notebook
with today's rules, and that half had to be safe enough to run without asking.

So tidying runs by itself, at the start of every map and every sync, and it
only does things that can be undone. A service page is moved to the archive,
not deleted. An address that is clearly the owner's joins the owner's page and
leaves an alias behind. A page someone investigated is never touched, because a
rule about an address should not overrule someone's work. Every removed line
is written to a log with its text.

The owner's copy is where "clearly the owner's" got its meaning. The map had
offered seventeen addresses as "possibly yours". Two were his. The other
fifteen were colleagues and friends who read his mail and answer somewhere
else, and one `--mine` would have folded them all into him. Never replying
looks the same from the headers whether the address is yours or your friend's. What differs is the name. His own addresses carry his name
or an address he already confirmed, and theirs do not. Now only those are
offered, and only those fold.

On a copy of his notebook, one pass archived 22 services, folded his 2
addresses and 3 duplicate skills, and removed 9 stale lines from 5 pages. A
second pass changed nothing.

The lesson we keep relearning: a fix to how data is made is half a fix, until
something carries it to the data already made.
