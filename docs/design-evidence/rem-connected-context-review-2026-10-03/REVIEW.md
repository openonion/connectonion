# Connected context provenance and hierarchy — 2026-10-03

Candidate in draft PR #2141; no release or deployment. Private notebook copies,
originals, native identifiers and screenshots remain outside the repository.

## Observed defect and correction

A read-only census of 386 raw Markdown records found 88 affected semantic pages:
219 explicit local links were absent or classified as mentions. There were also
78 relation pairs to other notes; that count does not establish that all 78 are
irrelevant. The broader 390-file hash ledger includes four operational files,
and is not a count of semantic pages.

The previous reader depended on title matching even for explicit local links,
excluded skill titles, and let an earlier reverse mention occupy a later
page's forward link. It could also take the first title mention's line as the
basis for a link elsewhere, assigning the wrong citations and privacy scope.

The candidate resolves exact existing notebook paths independently of labels
and target category. It takes basis, privacy and citations from the actual link
line, completes all forward entries, then supplies incoming navigation without
overwriting a page's own entry. Mention matching uses visible prose rather than
Markdown URLs; Sources trailers remain excluded. Citation numbers are unique,
in first-seen order, before the existing four-citation display limit.

All 219 baseline link losses/misclassifications are restored in the captured
notebook. All 386 records produce identical relationships with reversed input
order. All 390 ledger files remain byte-identical. This is structural navigation
verification, not a semantic relationship audit or proof that every link's
claim is supported. Each page pair still has one entry: a page's own weaker
mention can occupy the position of an incoming explicit link.

## Rendered experience

Cited conversations precede connection cards. Explicit links to people,
organizations, projects and skill catalog pages appear first. Other notebook
links and text mentions are separately folded, while their navigation remains
available. Labels describe links and mentions, without declaring a verified
relationship. Each card identifies the note containing its basis and opens
that note's citation, rather than the destination's citation with the same
number. Marked bases and their provenance footer inherit the same privacy flag.

Expansion controls have a 44px minimum height; basis copy is 13px with 1.5 line
height. A citation popover, title link and expansion remain distinct actions.

An independent AI reviewer uses a founder perspective with marketing and UI
experience; no human founder participation is claimed. Five actual pages cover
four page types, including two organizations, on desktop 1440px and phone 375px.
Default, expanded connections and Full memory states were captured. Initial
phone images used DPR 3 and some long Full memory/expanded images were difficult
to read completely; the final captures use DPR 1 on the same phone device
emulation. Rendered inspection and complete Markdown reading are distinct.

The independent reviewer visually inspected 97 images across stages: 24 baseline,
20 initial candidate, 30 final candidate, 20 final source/hidden states and three
real phone viewport rechecks of an unusually long project's Full memory. These
are stage inspections, not 97 distinct pages or a 97-state final pass. The final
53-image subset covers the five pages on desktop and phone, the origin-source
popovers, private states and the long phone note's selected scroll positions.
The viewport images are readable; a repeated tail in the long full-page image
is a capture limitation, not a demonstrated product defect.

The final flow harness actually opened an originating citation, hid and restored
already-open source content, and followed a connection card in each of ten
desktop/phone sequences. Eight marked basis/footer nodes hide and restore. All
ten sequences have no page errors, external requests or document/dialog
horizontal overflow. The independent reviewer inspected source-open and hidden
images; restoration and navigation are browser-harness checks rather than the
reviewer's manual computer actions. No new P1 was found in these inspected
states. Tablet, dark theme, broad navigation, keyboard accessibility, full-note
pixel coverage and all-original claim entailment were not reviewed this round.

| Priority | Finding and user impact | Evidence and concrete recheck | Status |
| --- | --- | --- | --- |
| P1 | Reverse mentions replace forward links and their provenance/private scope. | A real introduction, organization contact list and arbitrary-label fixture lose their actual link line. Reversing record order must preserve the exact kind, basis, citations and private flag. | Candidate fixed; full captured-record order check passes. |
| P1 | Exact skill links disappear because title matching excludes skills. | Three useful skill destinations are missing from an actual skill page. Exact paths and arbitrary labels must remain navigable; Sources-only and external URL text must not create edges. | Candidate fixed; three actual skill links restored. |
| P2 | Map/run/name hints crowd out useful links and original conversations. | An actual project shows six other-note cards before conversations; an organization hides 12 explicit contacts among mixed extra cards. Original conversations must precede folded hints, and actual explicit links must stay visible/expandable. | Candidate hierarchy corrected and independently rechecked in the scoped final states. |
| P2 | Repeated citation numbers inflate a card's source count. | An actual link line has four citation occurrences but three unique originals. Preserve unique numbers in order before the four-item limit. | Independent review finding fixed; red/green regression passes. |
| P2 | Whole-line basis includes neighboring claims and can clip the linked sentence. | Two introduction cards show an earlier attendance sentence instead of the introduction. Recheck link-local context against the original, preserving privacy and citation scope. | Remaining; no new semantic sentence parser. |
| P2 | A page's own mention occupies the single entry for an incoming explicit link. | The graph keeps one entry per page pair. A future representation must retain both directions' distinct provenance without silently replacing one. | Remaining; all incoming explicit links are not separately displayed. |
| P2 | Same-title project conversations and narrow multi-column summaries are hard to distinguish. | The inspected project has three same-title conversation buttons; long summaries clip at two lines. Distinguish each thread and inspect useful context at desktop and phone widths. | Remaining in #2065. |

## Verification and limits

Meaningful red regressions reproduced order-dependent provenance, omitted skill
links and conversation hierarchy. A later red regression reproduced repeated
source counts found by the independent review. Final focused unit gate: 25
passed in 1.45s. Focused browser gate: eight passed in 25.16s, including origin
citations, disclosure, source/conversation masking, consecutive marked sentences,
marked links/code and expanded private connection bases. These are targeted
gates; the entire browser suite and all notebook semantics were not checked.

The final rendered candidate uses the preserved real snapshot, with production
relationships recomputed and production render called after verifying unchanged
notebook hashes. This avoids repeating attachment extraction and does not
substitute invented page content. The four-citation limit and two-line card
clamp remain visible presentation limits.
Source popovers also retain bounded, unvalidated excerpts; they do not identify
an exact claim span.

Quota was 92% used against the configured 70% floor. No model investigation,
provider change or quota override occurred. Automatic generation/reconciliation,
all-page usefulness and unmarked privacy classification remain unverified.
