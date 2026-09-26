# A preview you can audit

Most of what ships in 1.8.9b8 is words. The code is `co audit`, one command
that asks of any CLI whether an agent could use it from its help alone. The
rest is what happened when we pointed it at ourselves.

The command took three rounds of design to get simple. It started as a check
over our own source. The first correction was to judge only what the program
prints, since that is all an agent ever sees. The second was to put rules
before the model, because most of what makes help usable can be decided by
reading text: is there an example, does it run this command, is every flag it
uses documented? The third was to stop treating `co` as special. `co audit
co`, `co audit gh` and `co audit yt-dlp` go through the same code, so the tool
we hold ourselves to is the one we can hold anyone to.

Holding ourselves to it was the useful part. The rules found four pages with
no example. The model found 114 pages it thought unclear or unrealistic.
Working through them found three pages that were simply wrong, and one gap
the model kept returning to, options with no description at all. That gap is
now a rule, because a rule is certain and a model is not.

The release picture shows both halves: `co` passing every rule on 281 pages,
and `yt-dlp`, a tool agents use every day, failing one because its help has no
example. Neither result is a judgement of the tool. It is a list of what an
agent would have to guess.
