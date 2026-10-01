# The phone number was on the page

The owner opened Ody's page in co rem to call him, and could not find the
number. It was there, under Contact, between the email and the
company. He had to read the page to find it, and he said what he wanted
instead: People should open like a spreadsheet, one row per person, the
email and the company and the phone in columns you scan. Then he asked the
question behind it. When `init` builds the map we write JSON files. Should it
be SQLite?

Our first answer was no. The notebook's own file module opens with "no
knowledge database", and the roster explains why: an index drifts from the
thing it indexes, and nothing tells you when it has. We had lived that. People
was 76 on one screen and 82 on another until one census counted for every
screen.

Then we looked at what a table would cost without one. Every row needs a
page parsed, a map row joined, and the census's verdict on whether the page is
listed at all. A chat view of a mail thread needs messages by id, in order,
and nothing addresses a message by id today: the headers are in one JSONL,
the bodies in 574 files named by a hash, a coding session's messages in
another JSONL per project. Each new view would write its own join, and we
would be back to two screens disagreeing.

So the turn was not "a database instead of files". It was a database that is
only ever a copy of the files. The pages stay the product; the JSON stays
true; `.state/rem.db` is rebuilt from them at the end of every map and sync,
group by group when an input file's size or mtime moved, and a failure to
build it is a line in the log, not a failed sync. Delete it and nothing is
lost. The drift the roster warned about cannot accumulate, because nothing
writes to the index except the thing that rebuilds it from the source.

On a copy of the owner's notebook it builds in 0.64 seconds, is 2.6 MB, and
the table has 330 rows: the census's 330, because it asks the census. Two
of those rows have a phone number. That is the next problem, and it belongs
to the investigation, not the index: a table makes the empty cells visible.

The lesson: when "should this be a database?" comes up, ask what has to stay
true. Here the files had to stay the truth, so the database became their
index, not their replacement.
