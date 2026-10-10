# Contact freshness, conditional actions and privacy — 2026-10-03

Candidate in draft PR #2141. No package release or publication.

## Source findings and candidate changes

A retained-mail date triage covered 36 person pages, excluding the owner from
contact-with-self comparisons. Four pages warranted a bounded original-source
review. This date triage is not a semantic pass of all 36 pages.

- Three pages used the UTC date where the notebook calendar had crossed into
  the following day. The four inspected pages were corrected manually, including
  their supported leads, Facts, History, cadence and source dates.
- Another page omitted newer allocations and a copied introduction. Its updated
  finding distinguishes the allocation, the teams' deadline, and an introduction
  copying the correspondent from a reply authored by that person. A copied
  introduction does not prove a completed kickoff.
- Requested screening documents were presented as a current debt. The originals
  establish a prerequisite and a conditional paid service, without a confirmed
  commitment to supply the documents or an accepted paid engagement.
- An old, genuine review promise was presented as a current overdue task based
  on age alone. The page now records the historical outcome as unknown within
  the reviewed mail. A shared invitation is qualified as such; calendar
  acceptances do not establish attendance or workshop delivery.

The person instructions now distinguish prerequisites from agreed commitments,
and historical missing outcomes from current debts. The date repair is narrower
than the manual corrections: only a bare First/Last contact date with exactly
one citation to the same extracted original can change. Qualified, multiple-source
or different-source interpretations stay. This repair does not normalize dates
throughout the prose or select a newer contact for an already populated field.

Facts citation lookup now compares complete source identities. A carrier email
cannot inherit an attachment citation merely because their identifiers share a
prefix.

## Actual reader findings

An empty retained calendar reply had saved headers but the reader reported its
original unavailable. The candidate preserves its subject, participants and
separate event/retrieval times, says **Mail headers**, and explains the absence
of body text without inventing a quote. All of that context respects the
existing private-content toggle.

Independent review found two confirmed privacy failures:

1. A marked sentence with a Markdown page link did not become a private span
   because the link target's punctuation interrupted sentence matching.
2. Connected-context basis text reused a marked private line as ordinary text,
   including when its 220-character clipping removed the marker.

Links and inline code are now protected before sentence privacy matching.
Relationship projections carry a private flag from the original untrimmed line
in both directions; collapsed and expanded connection bases respect it. Public
record titles and navigation remain available. One manually reviewed History
row also lacked its sensitive marker and was marked explicitly. These changes
do not establish automatic classification of unmarked private facts, or removal
of private content from the local HTML artifact.

Two phone insights were shortened after the initial rendered review folded
away the paid-service condition and the urgent-contact name. Both distinctions
now appear before the fold; full detail remains in Full memory.

## Independent AI founder/marketing/UI review

A separate AI reviewer checked the four selected pages' source meaning and
actual desktop (1440px) and phone (375px) structure, content and design: leads,
Facts, History/Activity, open-status interpretation, connected context, Full
memory, one selected source popup per person, and private-content states.

The first 26 candidate image checks span mixed candidate versions: capture files
were refreshed during review. They must not be described as a single final
26-state pass. Stable final captures were subsequently recorded separately:
26 page/source frames plus eight targeted privacy frames. The reviewer
independently inspected 12 stable final images: the two revised
phone first views, the header-only source shown at both sizes, and all eight
targeted privacy frames. The other 22 stable images were not individually
re-reviewed. Across stages, the reviewer made 42 image inspections: 26 mixed
candidate images, two confirmed privacy-failure images, two earlier phone-copy
rechecks and those 12 stable final images. No unresolved P1 was found in the
inspected final states; this is sampled coverage.

Protected originals, page bodies, native identifiers and screenshots remain
outside the repository. No private identities or case details are published.

| Priority | Finding / impact | Evidence and recheck criterion | Result |
| --- | --- | --- | --- |
| P1 | A conditional prerequisite and an old unresolved promise became current debts, prompting unsupported action. | Read the exact request/condition and later reviewed mail; retain unknown historical outcomes without asserting a current commitment. | Four sampled pages manually corrected; automatic writer acceptance pending. |
| P1 | Marked linked prose and derived connection bases remained visible when private content was hidden. | Confirm actual hidden DOM and rendered desktop/phone states; marked sentence, Activity detail and reused basis must hide and restore. | Candidate fixed; synthetic and actual targeted checks pass. |
| P2 | Contact chronology used the wrong calendar day, and newer copied context was omitted. | Verify exact event timestamp, notebook timezone and sender/Cc scope. | Manual pages corrected; narrow same-source date guard added. |
| P2 | Carrier facts could cite an attachment through a source-prefix match. | Exact-identity regression must allocate a distinct carrier citation and be idempotent. | Fixed. |
| P2 | An empty-body original appeared unavailable and lacked subject evidence. | Saved calendar source must show headers/subject and separate Sent/Retrieved times, no invented body, and hide/restore. | Fixed. |
| P2 | Phone folding hid a service condition or the urgent contact. | Actual 375px first insight must expose the condition/name before expansion. | Fixed and rechecked. |
| P2 | Compact last-contact summaries drop the copied-introduction qualifier. | Compare compact summary with qualified Facts/lead; future summary must preserve authorship scope. | Remaining. |
| P2 | Activity labels an allocation as a commitment merely because its line contains a deadline. | A team's deliverable must not become the owner's commitment. | Remaining; the inspected page creates no owed-action card. |
| P2 | Hidden mode leaves empty insight/Activity rows or punctuation without a clear hidden-content cue. | Actual final hidden desktop/phone; a future change should explain or collapse empty rows while keeping privacy intact. | Remaining. |
| P2 | Connected context precedes evidence and includes incidental keyword matches; mail counts lack explicit mapping scope. | Recheck hierarchy and relationship basis against actual source meaning. | Remaining. |

## Verification and exact limits

- **60 unique selected full mail originals**: 18 newly read retained originals,
  three newly read historical originals, and 39 prior full reads reused only
  after current canonical body hash and native identity verification. The
  reviewer read the 21 new raw originals, verified the 39 reused records, and
  reread eight recent cleaned allocation/introduction materials. Cleaned rereads
  are not another eight full original reads.
- A bounded historical metadata listing returned 22 rows and located all three
  missing historical targets. Only those three bodies were newly fetched and
  retained; 22 metadata rows are not 22 body reads. True current retrieval times
  remain distinct from historical event dates.
- The four changed pages have **35 citation/page pairs**: 34 mail originals and
  one carried-forward PDF citation. All 35 source contexts resolve; two are
  header-only mail contexts. The PDF was not freshly visually inspected here.
- Four people pages changed; **226 other entries** of the 230-entry page/state
  ledger remain byte-identical. Initial source inventory/archive and investigation
  cursors are unchanged. The three historical originals were retained separately
  and the derived database refreshed. Final protected page copies equal the
  actual notebook.
- Final focused unit gate: **212 passed in 7.06s**. Final focused browser gate:
  **7 passed in 18.89s**. Meaningful regressions failed before the respective
  date/citation, header-only and privacy fixes; intermediate gates overlap these
  final counts and must not be added to them.
- Stable final capture run: 26 frames over eight page/viewport sequences,
  no page errors, external requests or document horizontal overflow. Eight
  additional targeted actual frames assert linked sentence, marked History,
  derived connection basis and header-only evidence hidden/restored.
- Person instructions: **13,881 characters**; owner instructions: **14,987**,
  both under 15,000. No model rerun was made; the latest observed week meter was
  89% used against the configured 70% stop floor.

The other 32 person pages and owner were not semantically reviewed in this
round. Actual dark theme, tablet, search, broad navigation, every citation popup
and all notebook pages were not reviewed. The 640-character excerpt limit,
related-card semantics, automatic first write and automatic reconciliation
remain unverified. Manual corrections and passing regression gates do not
establish all-page usefulness.

[Issue #2190](https://github.com/openonion/connectonion/issues/2190) remains open
for automatic conditional-request and historical-promise acceptance. Draft PR
#2141 contains this candidate; no release was made.
