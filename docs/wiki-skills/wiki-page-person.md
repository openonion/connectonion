# Why wiki-page-person says what it says

The rules live in `connectonion/useful_skills/wiki-page-person/SKILL.md`, which
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
`co wiki list people --aliases` then found no `Our relationship` at all. The
`Contact` labels are read back the same way: a renamed label is an invisible
one, and the next batch meets the person as a stranger.

## The `Investigation:` line

A pass that rewrote it in its own words (2026-09-14) got a second, machine stamp
appended, and the line then said two different things.
