# The first run should remember something

The early REM first run mapped a mailbox and local coding sessions into pages,
then left most pages as empty frames. The map was useful infrastructure, but it
made the person wait before they could see why a memory notebook mattered.
Investigating only the owner's page helped; it still left the relationships and
projects that give that page meaning untouched.

We considered three first-run scopes: map only, investigate the entire notebook,
or investigate the people and work that have been active recently. The
whole-notebook experiment proved the investigation could run in parallel and
found reliability problems we have kept fixes for. It also spent effort on
older pages before the reader could show the current relationships a new user
was most likely to recognize. We chose the recent cohort.

`co rem init` now maps first, then uses the configured model to write the
owner's page, recent important people, active projects, and organizations
linked to those people. A selected person's investigation can search up to two
years of evidence, so “recent” chooses *who matters now* without erasing the
history of that relationship. The work is estimated and announced before model
use. Roughly 20% of the weekly runner allowance is the aim, not a hard stop:
the selected investigation can continue to completion. A configured weekly
safety floor still protects the rest of the owner's work when the runner has a
readable meter. For a runner without such a meter, the estimate remains an
estimate; REM does not pretend it measured that plan's percentage.

The `rem-init` Skill stays short. It invokes the CLI's first-run workflow and
checks the pages and logs. Detailed source and recovery instructions live with
the commands and investigation Skills, where they can be read when needed.

This choice has a tradeoff: old and quiet pages wait for a later investigation.
The map keeps them visible, and explicit commands and scheduled work can fill
them later. We will revisit the cohort rule when real first runs show that an
important person or project was omitted, or when a completed first run still
fails to put a useful, cited insight in the first view.
