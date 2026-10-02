# Held person pages: source and experience review — 2026-10-02

## Scope

Independent AI review from a technology founder’s marketing/UI perspective;
no human founder participation is claimed. Three real private person pages
were reviewed against seven complete archived primary emails. Private names,
addresses, message bodies and screenshots remain outside the repository.

No model call or quota override occurred. These pages were manually completed;
this is not evidence that fresh automatic initialization reliably resolves
held contacts or produces the same useful findings.

## Findings, fixes and recheck criteria

| Priority | Finding and user impact | Evidence | Fix and recheck |
| --- | --- | --- | --- |
| P1 | Metadata-only holds left useful relationship pages empty. | All three had two direct outgoing emails and no directly received email. Complete bodies and group metadata supplied concrete relationship history. | Manually complete the observed pages after full source review. Track the remaining automatic body-only review path in #2181; do not release all nameless outgoing addresses. |
| P1 | An exact recipient-header name was omitted, despite appearing in an archived third-party reply. | The direct address-only messages were counted correctly, while the friendly name was in another sender’s To header. | Retain recipient names separately, for existing direct contacts only. Regression fails before the fix and passes with either message order; no unrelated co-recipient page or extra direct received count. Offline replay matches the real seven captured header rows. |
| P2 | Group authorship and joint greetings could misassign identities, roles or contact details. | A third party supplied guidance; an outgoing signature contained the owner’s phone; a paired greeting did not explicitly bind names to recipient addresses. | Pass raw From/To/Cc alongside bodies; strengthen prompt boundaries. Keep unknown identity, role, phone and recipient language unknown unless supported. |
| P2 | Historical self-reports could be presented as current pending work or verified outcomes. | Sources described a dated submission report, travel plan and operational handoff. They did not establish acceptance, completed travel, inspected attachments or current execution. | Keep dates, reported status and missing outcomes explicit. The business list does not prove short-stay permissions; preserve that source limitation without adding a legal checklist. |
| P2 | Phone leads hid the useful finding behind introductory wording. | Independent visual review of all nine initial page heads found key submission/count details outside the three-line clamp. | Shorten the three manually reviewed Insight leads and put the useful finding first. Final capture asserts all three leads fit fully at 1440/768/375px; recheck actual heads visually. |
| P2 | Completed delivery was labelled Commitment. | A historical “You sent company introductions” row appeared in the Commitment filter. | Remove sent from the keyword classifier. A real browser regression fails on the original label, then passes: completed delivery is Conversation, an explicit promise remains Commitment and the filter works. Broader keyword semantics are not proven by this narrow fix. |

## Useful findings and source limits

- A university contact’s missed-mail exchange led to a third-party invitation
  and the user’s report of submitting three proposals. Acceptance, grading and
  allocation remain unverified; the third party’s role is not the contact’s.
- Another mailbox received company context followed by personal itinerary
  coordination. The observed greeting is retained with an identity qualifier;
  exact kinship, recipient language and completed travel are unknown.
- A business handoff reported 54 phone-ready prospects and 53 needing numbers,
  giving a concrete split between calling and data completion. Exact names
  are not bound by recipient order. Files, metrics and calling outcomes were
  not independently inspected.

The independent reviewer read all seven complete canonical mails and checked
claims against sender, recipients, dates and message identity. Source IDs
alone do not establish support. Outgoing language does not establish the
recipient’s Language, and an owner’s phone does not populate their Phone.

## Actual rendered coverage

All three real pages were captured at desktop 1440px, tablet 768px and phone
375px: initial head, expanded full note, and source 2 shown/hidden/restored.
The reviewer inspected all 45 initial screenshots. Source contexts were
independently matched to their canonical archive body prefix, sender and time,
then compared with the rendered dialog. Actual citation clicks, hiding,
restoring, closing and return focus were exercised in nine sequences.

After the short-lead and activity-label fixes, a separate final capture set
contains another 45 frames / nine sequences. All three leads fit fully at all
three widths; the completed delivery is Conversation. Final sequences report
zero JavaScript errors, external requests and horizontal overflow. Source times
use the Sydney notebook even with a Los Angeles browser timezone.

The independent reviewer inspected all nine final heads and nine final full
notes: 18 targeted final frames, 63 frames across the two stages. Short leads
fit fully and the Conversation label and source qualifications remain intact.
The 27 final source frames were exercised by automation, not independently
reinspected image by image. No new P0/P1 blocker was found in these three pages.
This is three-page coverage, not an all-page pass. Focus return and layout
assertions are automation results, distinct from visual/source review.

## Verification

- 166 focused unit tests passed in 6.62s: scanning, map/queue, people, mail
  archive, instructions and source boundaries. This includes the name-order
  regression and raw participant metadata passed to investigation material.
- Four browser tests passed, 18 deselected, in 9.90s: completed-delivery label
  and filter, source privacy/input limits, and notebook timezone.
- The activity regression’s final red run failed on the incorrect product
  label before the fix. An earlier test-script escaping error was corrected;
  it is not evidence of a product failure.
- Gates overlap earlier rounds. No new full-suite pass is claimed.

## Remaining work

| Priority | User impact and evidence | Concrete recheck |
| --- | --- | --- |
| P2 | Body-only names and relationship clues still encounter the nameless outgoing hold in a fresh automatic init. | Add an evidence-aware review path while retaining possible-owner and ambiguity protections; evaluate a fresh automatic run. #2181 remains open. |
| P2 | A source’s exact friendly recipient name is in raw snapshot metadata but absent from the body prefix shown in the dialog. | Offer bounded recipient metadata with authorship clearly separated; verify exact identity without requiring a model’s claim to be trusted. |
| P2 | Connected-context cards precede historical evidence and create a long phone band. | Rank supported, useful connections and disclose incidental ones; recheck phone structure and navigation. |
| P2 | A long email-only title wraps its final character onto a new phone line. | Improve title wrapping without inventing a display name; recheck 375px and narrower layout. |
| P2 | Long phone activity text can clip its ending or citation. | Inspect the actual row height and disclosure affordance at narrow widths; preserve access to its full dated note and citation. |
| P2 | A 640-character source prefix does not show every supporting clause. | Explicitly preserve the excerpt limit and consider bounded deeper reading; do not call the displayed prefix a validated claim span. |

Current inventory excludes the auxiliary skill navigation index: 36/36 person
pages, 9/9 organizations, 19/24 projects and 157/157 installed skills written.
Written counts do not prove semantic accuracy or usefulness. The project total
includes one private journal excluded by agreement; four ordinary project
writes await a resource choice. The calendar-only person finding and an old
temporary project finding remain Unknown. All-page source/usefulness review
is still incomplete; no release or package publication occurred.

Tracked in #2181, #2122 and #2065, within draft PR #2141.
