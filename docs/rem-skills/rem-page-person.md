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

## The lead, before `Facts`

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

## `Facts` is data (#2068)

A phone number inside a sentence cannot be found, and `Unknown` is the only way
the user learns that the mailbox never carried one. Ody's real page said "no
phone number appears in the material" while his signature carried one: the
turn searched evidence files for what it thought to look for. So the section
that was `Contact` is now `Facts`, with the fields a reader scans for
(location, time zone, links, how we know them, first and last contact), each
value cited, written first and rendered as a card; code reads the certain ones
(addresses, phones, links, dates) from the material before the turn and puts
back any the turn leaves off. The grammar is in `connectonion/rem/facts.py`.

Conference dial-ins are not contact numbers. Calendar invitations remain context
for the reader, but their telephone numbers are not automatically restored into
`Phone`. Genuine direct numbers need evidence of attribution to the subject.

## Held outgoing contacts and group authorship

Three real pages stayed as placeholders because direct metadata showed only
outgoing mail and no name. One contact's name was already in another sender's
To header, while his direct counts still correctly showed no mail from him.
Scanning now retains exact recipient-header names independently of direct
mail counts, including when the naming message occurs before the direct mail.
Co-recipients with no direct correspondence do not gain pages from this step;
nameless write-only addresses and possible owner addresses retain their guards.

The private archive hands over exact From/To/Cc metadata alongside the body.
The sender's reply or signature belongs to that sender, not every copied
contact. A joint greeting to two people cannot bind names to addresses by
their order. An owner's phone in an outgoing signature must not fill the
recipient's Phone, and outgoing English does not establish their Language.

The three observed pages were manually filled after primary-source review;
this does not establish future model reliability or verify referenced files,
business metrics, travel plans or current completion of historical handoffs.

## `Insight` is labelled

Two to four lines starting `Now:`, `Changed:`, `At stake:` or `Pattern:`. A
label makes the line say something of that kind; without one, a real page
filled the slot with "a key stakeholder who maintains regular communication",
which the inbox already said. The lead's first sentence is the balance (#2065):
who requested what, when, and any stated deadline. The reader derives age from
dates; a literal number of days in the page would become stale.

## `Language` is observed

Nobody states their working language in a signature. Waiting for them to is how
every English-speaking colleague came out `Language: Unknown`.

## Employment and affiliation are different facts

An address domain can identify an institution without establishing employment.
Five reviewed student collaborators had their university in `Company` even
though their messages established coursework affiliation. The candidate keeps
unstated employment `Unknown` and links the institution in relationship text.
Signatures can establish employment when they actually state it.

## Requests, approval boundaries and missing outcomes

The same five-page review found an instruction to update internal records
rewritten as an obligation to send a reply. A failure report acquired an owed
response without an explicit request or promise. Preserve the actual action;
these different messages do not establish the same obligation.

Approval of an integration pair does not approve a subsequent full scope
statement. Messages in a shared thread can concern different teams; match the
group and proposal before using an approval to close an ask. A request date,
reply cutoff and permission to proceed without a response are separate facts.
That permission does not prove the team proceeded, and a missing later outcome
does not establish a current blocker.

Source timestamps are converted on the notebook calendar. Explicit event and
deadline dates remain as stated. The reader gives an explicit due date priority
over request age and keeps it a due date after passage, without asserting that
the deadline was missed. A future meeting date alone is not a deadline.

These five corrections were manual reviews of 40 cited originals and 74 saved
messages across 28 exact provider threads. They do not verify automatic writer
reliability or complete correspondence outside those saved threads.

## `Why they are here`

It is the section most often missing and the one the user asks for most.

## Open threads

"Discussion status is not recorded" is not an open thread; it is a gap dressed
up as a finding.

Two professional-contact pages exposed a second boundary: an invitation was
still classified as an owed reply after an outgoing request for times, while a
next-cohort survey was treated as permission to complete an earlier term's
per-group assessment forms. Later replies must be read before naming a debt;
optional offers create none, and different terms/forms need separate closure.
Unknown booking or historical completion stays an explained gap, not a current
obligation inferred from age.

The same review found filled PDF FreeText annotations absent from ordinary
page text extraction. The candidate reads their text with page/type provenance
and marks non-text stamp appearances unread and unverified. A named collaborator
on the owner's side is not the copied liaison's personal signing entity. The
attachment source dialog identifies a current local file with unknown original
capture time and historical writer version. Text extraction does not validate
signatures or legal execution.

The [professional-contact review](../design-evidence/rem-professional-contact-review-2026-10-03/REVIEW.md)
records 53 full mail originals, two manual page corrections, selected PDF visual
pages and actual rendered coverage. It does not establish automatic reliability
or all-page acceptance.

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
