# Skill source excerpts and activity review — 2026-10-02

An independent AI reviewer used a marketing/UI technology-founder perspective.
This is a role-based review, not human-founder participation. Real notebook
content, screenshots and source paths remain private.

## Findings and corrections

| Priority | Problem and impact | Correction | Recheck criterion |
| --- | --- | --- | --- |
| P1 | Written skill pages cited sources that the reader could not expand. Users could not compare an instruction finding with its original context. | Keep only cited instruction/reference excerpts for accepted changed pages, up to 640 characters each. Verify full content against the source ID; preserve part identity and the complete digest. | Cited originals survive source removal and task cleanup; invalid hashes/parts, uncited text, private tags and secret shapes are excluded. |
| P1 | Repeated capture could overwrite the first source time or recovery scope. | Preserve the first capture under a maintenance lock; reject conflicting full hashes. Record recovery time separately from unknown historical source time. | Repeated retention leaves the entire first record unchanged; conflict raises an error. |
| P2 | Zero observed invocations appeared beside a recent Last active date taken from an investigation. This implied recent use. | Skill activity uses recorded invocation dates and says Last invocation. File updates remain separate; no invocation date is invented for zero/unknown usage. | Real zero-invocation pages omit the activity date; a used skill shows its actual recorded invocation date. |
| P2 | Investigated pages called unknown Current status sections Not investigated yet. This contradicted their completed investigation status. | Written pages say Still unknown and unresolved sections; mapped pages keep Not investigated yet. | Twelve real page-footer rechecks at three widths show the correction; a written-versus-mapped browser regression passes. |
| P2 | Instruction content could be read as proof of successful execution. | Label it Instruction excerpt and explain that instructions describe intended behavior, not a verified result. Recovery and truncation remain explicit. | Source dialog shows scope and unvalidated claim-span warning; private mode hides excerpt, scope and source description. |

## Verified recovery and limits

All 157 skill pages were checked for source identifier availability. Installed
main instructions match the cited content identifier on 156 pages. With bounded
own-folder reference files, **236 unique instruction/reference citation IDs** now
have saved excerpts. One main instruction has changed and remains unavailable.
The existing identifier stores a 16-hex prefix: the complete file is hashed
before comparing that prefix. The archives are owner-only files (0600), with
complete SHA-256 digest for conflict detection, part identity and recovery timestamp; original collection time is unknown and blank.

Skill pages cite **660 unique IDs** in total. **424 unique IDs remain unresolved**
(482 page/source pairs), including sessions, evals, run reports and investigation
context. Mutable current logs/reports do not substitute for historical originals.
Content-ID matching enables instruction recovery; it does not verify every claim,
source/version attribution or execution success. A 640-character prefix may omit
the specific supporting passage; it remains source context, not a validated claim
span. Refused or unchanged investigations do not create new captures.

## Rendered scope and checks

Four real skill pages cover unused instructions, bounded references, an observed
invocation, an unavailable session source and changed main instructions. The
actual reader/template/index was captured at desktop 1440px, phone 375px and
tablet 768px: 12 first-screen captures, 12 expanded full-note captures and 36 source
dialog captures (18 show/private pairs). Each source sequence checks hide,
restore and close. Zero JavaScript errors, external requests or horizontal overflow
were recorded. The independent reviewer inspected 60 initial images, then 12
targeted footer rechecks after the unknown-status correction. Updated full-page
captures remain local; the second review covers the changed footer, not a new
complete visual pass of every screenshot. These are four pages, not visual or
semantic coverage of all 157.

- Focused skill/reader/evidence unit checks: **34 passed in 7.09s**.
- Source scope, privacy and activity browser checks: **4 passed, 14 deselected in 9.79s**.
- Fixture phone views in light/dark themes: **2 passed, 15 deselected in 9.05s**.

The browser fixture verifies interaction contracts; actual notebook captures
provide the rendered evidence. Earlier fixture attempts exposed missing cache
invalidation, unopened note content and a CSS uppercase assertion; the fixture was
corrected without weakening the behavior checks. No new full REM unit gate or
all-page claim validation is claimed.

## Remaining work

Issue #2174 remains open for historical session/eval/run source access. Mechanical
Connected context cards and background state wording remain in #2065. The wider
person/project/skill usefulness audit is incomplete. Four prepared project writes
still await the user's model-resource choice; this round runs no REM model investigation,
overwrites no notebook prose and publishes no release.
