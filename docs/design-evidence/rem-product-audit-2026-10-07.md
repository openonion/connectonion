# REM: current product review, 7 October 2026

## What was actually checked

Public preview: a42. The a43 reader changes and init-help correction passed CI
and merged; its annotated tag starts the release workflow, which still needs
to pass before a43 is called published. This review rendered the existing real
notebook with that candidate reader, rather than claiming a fresh a43 init.
Private screenshots stay local. Ten frames cover Home, People, and written
Person/Project plus a mapped Skill at 390px and 1440px. There was no horizontal
overflow or browser JavaScript error. This is a small sample, not acceptance
of every page or screen-reader behavior.

The shared census counts mapped as **all listed pages**, including written
ones. The existing notebook has 78 mapped People / 7 written, 18 Projects /
3 written, 9 Organisations / 1 written, and 150 Skills / 0 written. These are
not results of a fresh complete initialization.

## Ten problems, ranked by harm to the REM promise

| Rank | Problem | Current evidence and best next step |
| --- | --- | --- |
| 1 | **The night can stop while the product says it is running.** | The real launchd job is installed/loaded with last exit code 1; newest saved run is 2 October. Status still advertises the next scheduled slot. Retain the prefix-integrity guard, diagnose/quarantine the changed source, continue safe sources, and surface last successful maintenance plus recovery. [#2301](https://github.com/openonion/connectonion/issues/2301). |
| 2 | **A failed first run does not reliably leave a useful partial memory or a short recovery path.** | The public a42 five-day sample took 672.34s, selected five writing tasks, timed out four and received one auth refusal, writing zero pages. a43 reports failure on Home; runner access preflight, circuit stopping and actionable per-stage recovery remain. A newly successful minimal model request does not rerun that acceptance. [#2302](https://github.com/openonion/connectonion/issues/2302). |
| 3 | **Written, identified and trustworthy are still easy to confuse.** | A sampled written Person is styled Investigated while its lead explicitly cannot establish whether the sender is human or automated. Only 7 of 78 listed People have written pages. Preserve unreviewed contacts in the directory, distinguish identity confidence from investigation completion, and consolidate aliases without asserting ambiguous matches. [#2057](https://github.com/openonion/connectonion/issues/2057), [#2200](https://github.com/openonion/connectonion/issues/2200). |
| 4 | **All-history discovery and all-history understanding do not have a dependable completion/cost contract.** | One complete metadata scan took 844s; the earlier public-wheel scan took 3h47m and failed. a42 retains completed years, but durable resume of only failed windows and measured full-cohort writing remain unproved. First-investigation windows can be 730 days even when mapping uses a shorter lookback; scope and estimates must explain both. [#2176](https://github.com/openonion/connectonion/issues/2176), [#2298](https://github.com/openonion/connectonion/issues/2298), [#2260](https://github.com/openonion/connectonion/issues/2260). |
| 5 | **The product cannot yet earn trust in its claims and obligations.** | A sampled Project first fold promotes a historical request as OPEN while also explaining the sample did not confirm current work. Existing claim-overstatement issues and the 30-claim original-source audit remain unresolved. Distinguish requests, accepted commitments, uncertain status and resolved items; verify claims against original evidence, not citation presence. [#2231](https://github.com/openonion/connectonion/issues/2231), [#2195](https://github.com/openonion/connectonion/issues/2195), [#2207](https://github.com/openonion/connectonion/issues/2207). |
| 6 | **The morning does not yet show demonstrated new understanding.** | The real notebook's latest 20 logs contain no claim_changes. Home can show a rewritten page from 2 October, rather than a demonstrated new fact with a before/after and reason. The code already supports claim cards; it still needs a real overnight pass that produces a verified, useful change and suppresses no-ops. [#2096](https://github.com/openonion/connectonion/issues/2096), [#2112](https://github.com/openonion/connectonion/issues/2112). |
| 7 | **Phone hierarchy spends too much attention before the useful return.** | At 390px, Home's morning panel begins at y404, first memory card y706, and recall y1583. Zero overflow is insufficient: navigation, repeated headings and explanation push the remembered context deep. Put one useful change/action/recall in the first viewport and audit touch/focus targets, including the small inspection link. [#2292](https://github.com/openonion/connectonion/issues/2292), [#2065](https://github.com/openonion/connectonion/issues/2065). |
| 8 | **Record detail remains a document to read, rather than an activity/state to explore.** | One written Project renders a 17,890px phone document. That length alone is not a defect, but full prose and History still lack the typed event/time filters needed to reach a meaningful turn. Keep a short state/decision layer, typed activity with exact originals, and intentionally disclosed full detail. [#2103](https://github.com/openonion/connectonion/issues/2103), [#2105](https://github.com/openonion/connectonion/issues/2105). |
| 9 | **Context navigation exists but is not yet a fluent way to follow the work.** | The sampled Project has five relation links, but Connected context starts at y2064 on phone. Code already supports incoming and outgoing links, so saying there are no links would be wrong. Bring relevant connections into the task flow, keep explicit references distinct from mentions, and prove return-to-mention, rename/merge and source navigation on real records. [#2197](https://github.com/openonion/connectonion/issues/2197), [#2098](https://github.com/openonion/connectonion/issues/2098). |
| 10 | **Recall is a reveal interaction rather than a durable remembering loop.** | recallPrompt sorts candidates, picks the first, and toggles visibility. It does not record Remembered / Later / No longer useful feedback, or change tomorrow's selection from that feedback. Persist explicit, erasable owner feedback with scheduling and cited answers; verify over several mornings. [#2097](https://github.com/openonion/connectonion/issues/2097). |

## What “mature” means here

The stable-release gate [#2296](https://github.com/openonion/connectonion/issues/2296)
requires measured cost, citation, coverage, identity, project, runtime and owner
checks. It explicitly leaves some reader/recall capabilities open. The broader
[product maturity audit](rem-product-audit-2026-10-01.md) also requires a bounded
night, verified morning changes, asking/correcting memory, task retrieval and
recall over several days. Passing the release gate must not be presented as
passing that broader product bar.

The next implementation priority is night health and recoverable first-run
failure, followed by identity/source truth, then morning presentation and
activity/navigation. The desired aha is: REM notices a supported change or
connection, explains why it matters now, and lets the owner reach its original
or correct it. Attractive cards alone do not establish that behavior.

CI has a separate engineering problem: release preparation triggers duplicate
push/PR matrices despite parallel Python jobs and pytest workers. The current
PR run took approximately 12 minutes from creation to completion. Track
critical path and duplication in [#2134](https://github.com/openonion/connectonion/issues/2134);
do not remove coverage or immutable-tag verification to shorten it.

## Access changed during the review

Both source-free probes now succeed: the standard `sonnet` alias took 11.8s,
and configured `claude-sonnet-5-5` took 11.92s (exit 0, result OK, reported model
matches). No ambient Anthropic API key was used. The previous authentication
403 must not be repeated as the current diagnosis. The next real-writing
sample can now separate source-gathering timeouts from model or prompt quality;
it has not yet been performed by this review.
