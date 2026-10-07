---
description: Why co rem's first run works through every eligible page in its 90-day map, and how model access and nightly health stay visible when work cannot finish.
tags: [REM, Memory, Product design, Reliability]
---

# A first run must finish its map

This account accompanies the stable co rem 1.9.0 release.

A memory product can discover a person, show their name in a directory, and still
know almost nothing useful about them. That was the gap in co rem's first run:
the map counted people and projects, but a quota gate could leave much of the
directory as outlines. The user asked for one command that investigated every
eligible person in the 90-day window and showed its progress while doing it.

## The choice

We considered keeping a small default cohort and asking users to run
`investigate all` later. That made the first result faster, but it turned the
most important promise into a second command. We also considered retaining a
weekly percentage stop. It protected model allowance, but the completed map
then overstated what the notebook actually knew.

The foreground first run now selects every eligible mapped Person, Project,
Organisation and installed Skill. Optional `--first-*` caps remain for a
deliberate trial. Ten workers share the page queue, and the terminal reports
mail, page and category progress. The estimate is shown before model work; it
is a planning figure, not a hidden stop. The provider can still enforce its
own limits.

## A schedule is not proof of health

A prior installed nightly job could repeatedly fail on a rewritten coding
session while status said it was running. The importer still protects its
checkpoint: a changed consumed prefix is never treated as a safe append. It
now records that file as skipped and continues with other sessions, and status,
doctor and the reader surface a failed or warning-bearing scheduled pass.

Model access is checked with a source-free turn before the page queue. If it
fails, the map and saved mail stay available, the failed check is visible in
the run history, and init does not install nightly upkeep. A provider refusal
after the queue starts stops new pages; already running pages finish.

## Evidence and limits

The public a43 wheel's 90-day owner trial mapped 3,362 Gmail and Outlook
messages, then completed 67 eligible People, 17 Projects, 18 Organisations,
154 Skills and the owner page in 52m 57s. All 258 page runs finished; none
failed. In four sampled written pages per category, all 161 numbered source
IDs opened a retained local excerpt. That checks source availability, not every
claim's meaning. The browser review covers selected desktop and phone views,
including People, Projects, Organisations and Skills; it is not an all-page
claim.

An installed stable candidate then resumed the existing notebook: 16 of 17
pending pages were accepted, while one Project failed its cited-claim audit.
The prior page remained intact. A scheduled trial later reached the same
refusal; status now reports that full-pass failure. Automatic bounded retries
of these quality refusals are tracked for 1.9.1.

Two limits remain material. A contact held for identity review does not become
an investigated Person until the owner confirms it. A changed transcript is
kept out of the nightly import while its checkpoint remains intact; a safe
reviewed reindex path is separate work. We would revisit the ten-worker
default if real runs show provider throttling, memory pressure, or poor page
quality that improves with less concurrency.

See the [co rem guide](/cli/rem) for the current commands and
[release channels](/releases) for the published artifact.
