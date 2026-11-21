# An empty search is not an empty workspace

*2026-11-15*

The first question after `co notion` worked was not about reading a page. It
was "where is the list of everything?" The answer at the time was
`co notion search ""`: an empty query, which Notion's search treats as "all of
it". It worked, and nobody would ever have typed it. Two commands that did the
same thing, one of them hidden behind a blank string, is exactly what a reviewer
had just flagged on another source, where `notes` and `ls` listed the same
notes. So listing became its own command, `co notion pages`, and `search` now
refuses an empty query and points at it. One command per job.

The harder part was what "everything" means. A Notion internal connection
reads only the pages someone gave it; a page nobody gave it does not exist as
far as the API is concerned. We had written every message around that, and
then the first real run listed twenty pages without anyone picking one. The
key was a personal access token, which reads whatever its owner's account can
read. Both are honest answers to "what can this key see", and neither is "your
workspace". So `pages` cannot say "these are your pages", and an empty
`search` cannot say "there is no such page". Both outputs end with the same
sentence: this is what this key can read, not a list of the workspace. When a page is missing, the `Next:` line is
`co notion check --target <link>`, which tells a working key from an unshared
page instead of leaving an agent to conclude the page was deleted.

The same honesty had to hold for the long cases. Notion stops one query at
10,000 results and stops giving cursors, and it marks the response
`incomplete` — sometimes before the last page it does send. An early version
read `has_more: false` as "done". Now `db` says that Notion stopped the query
and its `Next:` line narrows it by edit time, and `--json` carries
`complete: false` rather than a silent short list. A page read that hits its
block limit says `INCOMPLETE` and what stopped it.

This change ships only the reading half. Writing pages, signing in through the
browser and Notion as a notebook source exist on our side, but each brings its
own questions — preview and confirmation, a service that does not exist yet,
a shared hook for every source — and each deserves its own review. A tool that
reads carefully and says what it could not see is useful on its own, and it is
the part everything else builds on.
