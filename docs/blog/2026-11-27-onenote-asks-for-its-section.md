---
description: The first OneNote source would only read pages REM had approved in a state file nothing could write. Rewritten after the Granola fix, co onenote changes and show take --section on the command line and read one section live.
tags: [REM, OneNote, Sources, CLI]
---

# OneNote asks for its section

Our first OneNote source for `co rem` was careful in the wrong place. Before
`co onenote changes` would read anything, it opened `.state/subscriptions.json`,
looked for an approved Microsoft account and a list of page IDs, and refused
to run without them. The tests passed, because the tests wrote that record
themselves. On a fresh machine nothing wrote it. `co rem sources` had no way to
create a OneNote selection, so the command told you to approve OneNote in a
place that could not approve it. The pull request was closed for exactly that:
no setup path a new user could follow.

Granola had the same catch-22 and was fixed first. The fix turned the design
around: the source command owns scope and REM owns consent. `co granola` takes
`--folder` on the command line and never imports REM. OneNote now does the
same with the unit OneNote already has, a section:

    co onenote ls --ids
    co onenote changes --since 2026-11-20T00:00:00Z --section 1-example --json
    co onenote show 0-example --section 1-example --json

`changes` lists only page metadata in that section, oldest change first,
inside `{since, until, items}`. `show` reads one page as text, and with
`--section` it refuses a page filed anywhere else before fetching its content.
The section has to be in the signed-in account's own notebook list.

One choice came from being honest about what had been tried. Graph can filter
pages by modification time, but no real account here has run that query, and
it would be the first failure a user saw. `co onenote pages` already sorts by
`lastModifiedDateTime` newest first on real notebooks. So `changes` reads in
that order and stops at the first page not newer than `--since`, which costs
one request when little changed. More than 1000 changes is refused rather than
cut short, and a rate limit that does not clear fails the read instead of
returning the pages it got.

The lesson is the one Granola taught: a check that only a fixture can satisfy
is not a safety check. It is a command nobody can run. Scope on the command
line can be read in the shell history, tested by hand, and narrowed by REM.
