# Private project status and explicit requests — 2026-10-03

Candidate in draft PR #2141; no package release or publication.

## Observed problem

The inspected notebook had 22 written of 23 mapped projects. Its one unwritten
project matched the existing private-folder rule. Both the retained-session
queue and the first-run file fallback already excluded that page: no scheduling
bypass was found. Status nevertheless named it as ordinary pending work and
suggested `investigate projects`, a command that deliberately skips it.

The actual mapped page compounded the confusion: its lead was a local path,
and the generic callout did not explain the intentional hold.

## Candidate changes

- Keep the truthful 22/23 written count and existing census/JSON fields.
- Show a count-only explanation for unwritten private projects and leave them
  out of the ordinary category next action. With no ordinary backlog and the
  service off, both human and JSON status next actions now say `start`.
- Use the existing Python private-folder rule in the reader snapshot. For an
  unwritten private project, lead with the reason automatic investigation skips
  it and the need to name the page to request a write. The short explanation
  is fully visible on the phone; its existing named-page command is retained.
- Correct an adjacent stale browser assertion to the actual existing
  “Recorded direction” heading; that wording was already present at the prior HEAD.

No private original body was read and no private page was written in this round.
Mapping may already have read metadata or retained source material; this round
does not prove that private content has never been read. An explicit request
remains necessary for that page's write.

## Independent AI founder/marketing/UI review

A separate AI reviewer inspected actual structure, content and design on the
project index and mapped private project, collapsed and with Full memory
expanded, at 1440px and 375px. The reviewer inspected 18 captures across stages:
six baseline, six intermediate candidate and six final, plus human and JSON
status. These represent six page/viewport states repeated across the stages. These sampled views do not establish all-page usefulness or correctness.
Protected captures and exact notebook ledgers stay outside the repository.
Dark theme, tablet layout, index filter/copy interactions and broad navigation
were not reviewed in these actual-notebook captures. Private originals and the
automatic writer were not exercised; the synthetic browser gate covers only
its named assertions.

| Priority | Finding / user impact | Evidence and recheck | Result |
| --- | --- | --- | --- |
| P2 | Status suggested a category command that cannot write the remaining page. Users could repeat an ineffective action. | Actual human/JSON status and mixed/only-private regressions; preserve mapped/written counts, exclude only private backlog from category next action. | Fixed. |
| P2 | A local path filled the private page's lead and the callout hid the reason it waited. Users could read an intentional hold as a failed investigation. | Actual desktop/phone mapped page; explicit-request reason must appear in the lead, automatic skip in the callout, existing named-page command retained. | Fixed. |
| P2 | The phone initially folded away the final request instruction. | Actual candidate phone lead; the complete reason and next action must be visible without expanding. | Fixed and rechecked. |
| P2 | Phone project table requires sideways scrolling to see status/activity; its index does not explain the private hold. | Actual 375px index; any future change should expose these fields or a clear scroll cue. | Remaining, outside this focused change. |
| P2 | Connected context is ahead of the lower command callout. | Actual mapped page collapsed/expanded; future hierarchy work should keep the primary action easy to reach. | Remaining; lead now provides the reason first. |

## Verification and limits

- Two meaningful CLI regressions failed before the status change.
- Rendered private-page regression failed on the raw-path lead before the UI change.
- CLI, census, project pages and first-run gate: **189 passed in 46.39s**, with a
  normal terminal environment. The first run under `TERM=dumb`/`NO_COLOR=1`
  passed 187 and failed two terminal animation tests; standalone reproduction
  confirmed the environment mismatch. No terminal implementation was changed.
- Reader/census unit gate: **16 passed in 1.21s** (overlaps the prior census gate).
- Focused actual browser gate: **4 passed in 9.72s** (private mapped desktop/phone, first finding, start-date Unknown and project/context navigation).
- Six final rendered states: no page errors, external requests or document
  horizontal overflow. The phone table still has its own horizontal scroller.
- All **230** notebook page/state ledger entries remain byte-identical.
- The week meter was **89% used**, above the configured 70% stop floor. No model
  rerun, provider-body retrieval, automatic writer acceptance, package release
  or all-page semantic pass is claimed.

Issue #2079 remains open for its broader initial-run/privacy/map concerns.
