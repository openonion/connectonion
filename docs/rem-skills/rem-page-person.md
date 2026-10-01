# Why rem-page-person says what it says

The rules live in `connectonion/useful_skills/rem-page-person/SKILL.md`, which
is composed into every model turn that writes a person's page. This file holds
the reasons, incidents and measurements behind those rules. It is not loaded at
runtime, so the Skill stays short enough to leave the turn room for the page
(#1851).

## The input is the page and the material

Measured on real runs, the search for example pages, earlier outputs, logs,
other skills or repository files to copy a format from, not the writing, used
up the turns, and the page was never written. The shape is in the Skill, so the
search buys nothing.

Writing the page once, checking once and fixing in one edit exists for the same
reason: polishing it line by line spends the turns the page needed.

## Why the page never shrinks

This is the page the user will open most, and the one most likely to come out
thin. It is the memory of a relationship, not a summary of one.

## The lead, before `Contact`

The first screen of a real page (#1974, 1.9.0a2) was eight contact fields; the
one open thread was at line 33 and the page had no last-contact date at all.
#1580 asks for a page that is light on top and deep below: someone opening a
person's page wants, in order, who this is to them, what is open between them,
and when they last spoke. The lead is those three things in 2–3 sentences,
cited like everything else, and the sections below keep the detail. It has no
heading so the roster's section list is unchanged; `stub_person` writes it as
`Unknown — not investigated yet. Last contact: Unknown.` so a mapped page
already has the slot, and the validator reads it as ordinary cited text.

## Every section is always present

An empty slot is information: it tells the user what to go find out. A page
that omits a section hides the gap instead, and the one-line person page is
exactly what dropping sections produces.

## `Contact` is fields

A phone number inside a sentence cannot be found, and `Unknown` is the only way
the user learns that the mailbox never carried one.

## `Language` is observed

Nobody states their working language in a signature. Waiting for them to is how
every English-speaking colleague came out `Language: Unknown`.

## `Company` from the domain and signature

Both are already in the material: the address domain names the institution and
the four lines under "Thank you," give the department, the office and the
direct line. Institutional facts are kept on the organisation page so they are
written once rather than drifting across every person who works there.

## `Why they are here`

It is the section most often missing and the one the user asks for most.

## Open threads

"Discussion status is not recorded" is not an open thread; it is a gap dressed
up as a finding.

## Marking inference

A judgment drawn from how someone writes is worth keeping, and worth labelling,
so a later pass does not harden it into a fact.

## A silent section stays `Unknown`

"No prior history", "relationship not yet established" or "communication style
cannot be assessed" are not findings, only the gap in other words, and they hide
the gap the `Unknown` shows.

## `Uncertainties`

It is where a thin page becomes honest instead of short.

## The headings are copied exactly

A stage handed this shape with notes beside the headings wrote
`## Our relationship          state and shape, not a log` into a real page, and
`co rem list people --aliases` then found no `Our relationship` at all. The
`Contact` labels are read back the same way: a renamed label is an invisible
one, and the next batch meets the person as a stranger.

## The `Investigation:` line

A pass that rewrote it in its own words (2026-09-14) got a second, machine stamp
appended, and the line then said two different things.

## The owner's page (`rem-owner-page`)

The owner's page is a person's page with its own lead, composed only for
`co rem investigate me`. On the 1.9.0a6 acceptance notebook it said "Claude
Code owes the user a message-volume check" and "Codex owes the user a
status", and its `Last contact` was a Claude Code session (#2027). A session
is the owner talking to a tool, so what they asked for is what they were
doing: it belongs in the lead and `History`, never in `Open threads` as a
debt. The same page named no project of the last weeks while its Skill asked
for them, and cited 3 of 1,477 session messages. The map already knows each
project's sessions and dates, so the owner's turn now gets them as a
`recent-projects` item (the four weeks before the map's own date, newest
first), and the lead names the busiest, dated.
