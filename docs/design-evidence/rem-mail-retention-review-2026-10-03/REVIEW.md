# Mail citations: private originals and truthful recovery

Candidate in draft PR #2141; tracked in #2187. The independent reviewer is an
AI using a technology-founder perspective with marketing/UI experience, not
a human founder. Private identities, native IDs, mail bodies and screenshots
are excluded from this public report.

## Observed problem and source scope

Four previously reviewed person pages contained 30 mail citation/page pairs,
covering 21 unique cited messages. Fourteen exact older cited renderings were
unavailable in reader source context: three on one page and eleven on another.
The provider text had already been retrieved for the preceding audit but was
not indexed in the notebook. Live gathering also discarded original provider
renderings after cleaning quoted material for investigation.

This round recovered those 14 previously retrieved renderings, comparing each
full body and native identity hash against its private audit file. Original
retrieval timestamps and provider thread identity were not recorded. Neither
file modification time nor the new retention time was substituted for them.
No new provider query or investigation model call occurred. All 30 citation/page pairs now
resolve, without changing any person-page text.

## Candidate changes and significant review findings

| Priority | Problem and user impact | Evidence and correction | Recheck criterion |
| --- | --- | --- | --- |
| P1 | A citation could remain while its original disappeared, preventing inspection of the claim. | Live gathering now retains full private provider text; the writer receives that same retained body and headers. Historical recovery restores the exact 14 renderings. | Cited sources resolve after temporary investigation material is removed; repeat reads preserve the first rendering and supplied headers. |
| P1 | Putting later captures in initial mail directories would inflate coverage and mix older correspondence into initial organization material. | Independent review identified the directory-scan risk; a red test reproduced a changed saved-body count. New snapshots and thin metadata are isolated from the initial archive. | Initial inventory/manifest, saved count and domain-material digest stay unchanged. |
| P1 | A correct index identity could point to a file containing another message. | Independent code review found that archived mail trusted the pointer. Wrong-provider and wrong-native-ID cases now reject source context. Canonical location is selected inside the maintenance lock. | Both mismatch regressions return unavailable, rather than another mail's body. |
| P2 | Provider headers could use up the entire short excerpt, hiding useful body text. | Mail excerpts begin after the provider's Email Body delimiter; full raw text remains unchanged. | A long-header fixture displays the first body clause; body-prefix length and truncation remain truthful. |
| P2 | Unqualified timestamps could make a recovered capture look like evidence available during the original investigation. | Source metadata distinguishes Sent, Retrieved and later Archived time. Historical recovery keeps original retrieval unknown and exposes its coverage limits. | Recovered fixtures show Archived and unknown original retrieval, with no fabricated Retrieved time. |
| P2 | Long participant headers and provenance text overwhelmed the phone source dialog. | From/To/Cc default to a private disclosure with a 44px target; historical scope copy is shorter. | Default phone state shows the body, while expanded raw headers remain readable and private. |
| P2 | Scrolling a long source body hid the Close button on phone. | Review identified this in actual final source views; the source header is kept visible while scrolling and Close has a 44px target. | Close remains in the viewport after scrolling the body and restores focus to the citation. |

Saved snapshots are provider-rendered text, not original MIME. A short message
identity is not a body-revision identifier or proof of claim correctness.
The reader still presents a prefix, explicitly not a validated claim span.
Participant headers do not assign tasks or prove individual attendance.

## Private isolation and actual rendered coverage

The private recovery audit matched all 14 full renderings, headers,
empty retrieval timestamps and separate retention timestamps. Initial
inventory and manifest bytes, all 1,926 original snapshot hashes, the actual
247-item organization material source/text digest and all 36 person-page text
hashes stayed unchanged. New files and their directories are owner-only.
This round checks their complete bytes and metadata against the preceding
audit; it reuses that audit's semantic reading rather than claiming a new
all-history semantic review.
The independent reviewer separately recomputed the 14 exact body/native
identity comparisons and checked current inventory, manifest and person-page
hashes. The private recovery audit records the broader initial snapshot and
organization-material invariance; the reviewer did not independently rerun
that entire before/after comparison.

Independent review inspected the two affected source cases on actual desktop
and 375px phone pages. Stage coverage comprises 20 baseline frames, 20 initial
after frames and 20 targeted final frames: page heads and complete notes,
unavailable sources, default collapsed recipients, expanded recipients,
scrolled body and shown/hidden/restored privacy states. A subsequent six-frame
recheck covers the scrolling Close correction and default phone layout.
These are stage views of two source cases, not 66 different pages or a review
of every citation. The four focused browser checks use synthetic fixture data.

The harness records no JavaScript errors, external requests or checked
horizontal overflow. Raw headers, clocks, source limits and excerpts hide
together with private content. Citation focus is restored when Close is used.

## Verification and remaining gaps

- 132 focused unit tests passed in 8.10s across investigation, archive, index,
  reader model, reader and reader design.
- Four focused browser checks passed in 11.55s, covering recovery clocks/headers,
  scrolling Close access, privacy while dialogs are open, notebook source time
  and input limits. The final six-frame actual Close recheck also passed.
- Red regressions reproduced missing live participants/retention, initial
  coverage pollution and mismatched snapshot identity. Browser regressions
  reproduced absent participant disclosure and inaccessible scrolling Close.

Remaining P2: the 640-character prefix may stop before a decisive condition,
or enter quoted history and long links. Raw provider spelling and formatting
are preserved. The unknown provider threads use existing subject/counterpart
grouping; this is not an exact provider-thread guarantee or complete history.
Other pages, source types, themes and every citation were not visually audited
in this round. Recovery does not establish automatic generation quality or
all-page usefulness. No release or deployment is claimed; the Design Journal
entry remains a draft.
