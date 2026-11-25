# A number is only as good as the list it came from

*2026-11-24*

The first thing a person did with the merged `co notion` was list their
pages, and the second was ask why every row started with
`40d30235-c573-808d-a4c4-fc76be8fe50d`. Notion names a page by a 32-character
id, and `page`, `db` and `columns` wanted that id typed back. Nobody types
that. Copying it from a terminal is the kind of step an agent gets right and a
person gets wrong.

So lists are numbered now, the way `co asana` and `co onenote` already number
theirs: `co notion pages` prints `1.`, `2.`, `3.`, and `co notion page 2`
opens the second. The ids are saved for fifteen minutes in the same listing
store those commands use, bound to the key that listed them; `--ids` and
`--json` still show every id.

What a number means took longer than adding it. The rule we kept is the one
the other commands keep: a number is a row of the last list shown. After
`co notion db 5` the numbers are that database's rows, not the databases. We
watched that rule bite on the first real run: `co notion add 1` right after
listing a database's rows sent a row, a page, where a database belonged, and
Notion answered in its own words that a page is not a database. The answer
was not to make numbers cleverer. It was to say what happened: the error now
names the page, says a number is a row of the last list, and points at
`co notion pages --type database`.

A page opened with `co notion page` showed its relation columns as a run of
ids, where Notion shows the linked pages by title. Notion's API gives only the
ids, so each title is one more read. In a page that is a handful of reads; in
a `db` list of twenty rows it could be a hundred, against a rate limit of about
three a second. So a `db` row says "4 linked", and a page lists the linked
pages by title under its properties, numbered with its child pages so the
next `page 2` opens one. At most 25 titles are read; a linked page the key
cannot read is counted, never named by guess.

Two smaller changes came from the same session. Lists now ask for 100 rows, one
Notion request, so most of them are whole; a `--cursor` carries a check of the
list it came from and is refused on a different one, as Gmail's mailbox
cursors are. And `page --md` prints a real Markdown document, front matter
and all, because the plain view was only Markdown-ish: tables had no header
rule and bold text lost its marks. The terminal view now renders that same
Markdown the way `co obsidian` renders a note, under a header laid out like
`co asana task`'s: the title and id, the times labelled, then Properties.
