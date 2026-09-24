# Wiki investigation and maintenance improvements — 2026-09-22

This follows the [initial test findings](wiki-investigate-20260922.md), using the
same synthetic Atlas source material and the same Luna generator. No user Wiki,
mailbox, scheduler, historical queue or release was touched.

## Changes

- A populated project Overview requires a closed fenced flow. An explicit
  Unknown statement remains valid when the evidence cannot establish a flow.
  This checks presentation, not factual entailment of a diagram.
- Numbered references cannot bundle multiple existing backticked local files.
  This catches the observed input/output bundling; it is not a general citation
  parser for every URI, prose format or remote file.
- Investigation/maintenance preserve script-mapped Sessions, First seen and
  Last seen fields. Mapping remains responsible for updating those observations.
- Project instructions distinguish an explicitly recorded decision from current
  behavior. Missing decision evidence stays unknown; a real dated choice is retained.
- Maintenance edits a disposable notebook, checks all changed entity pages and
  write policies before promotion, rejects deletion, and compares the live snapshot
  under the maintenance lock. The sync service already holds that lock and passes
  that context explicitly. Standalone maintenance acquires it for promotion.
- Failed validation preserves live pages, pending corrections and measured usage.
  This is protection against bad generated edits, not an OS sandbox or a multi-file
  transaction resilient to every filesystem failure during promotion.
- Removed contradictory maintenance instructions saying only person-page layouts
  were fixed. They conflicted with the canonical project template.
- The source checker recognizes exact supplied file:// references. Reflection
  envelopes now carry their explicitly attributed source references, including
  compact views; exact files are recognized without admitting neighboring files.
  Identifiability does not establish source truth or retrieval.

## Retained failures and follow-up

The first replay added diagrams and split file citations, but still blurred current
behavior with a decision and dropped mapped counts/dates. Both output and usage are
retained. The metadata guard and stronger decision instructions followed that finding.

The second replay kept the metadata, diagrams and separate citations and explicitly
said no recorded decision was found. It was initially rejected because source [5]
used the exact supplied session file instead of its source ID. The file:// validation
fix accepts that supplied file. The original failed result remains unchanged, and a
separate deterministic revalidation accepted the retained candidate without a new
model call. The input material is exactly the earlier baseline's; the synthetic
ownership file from a later correction test was held outside the source directory
during replay and restored afterwards so the original four-file evidence set matched.

A live correction counterexample supplied a genuine dated local-pilot decision and
Mira ownership. Before maintenance staging, the model applied the owner correction
but replaced the canonical page with a short summary, losing headings, citations and
diagrams. That bad output was retained and led to the disposable-maintenance fix.

The first staged maintenance candidate retained the canonical structure but was
rejected for the correction's actual source file: the reflection envelope had not
exposed its source references to validation. No page was changed and the correction
remained pending. The explicit-reference propagation fix followed; no evidence was
fabricated or silently exempted from the checker.

## Regression and evidence

Wiki unit/CLI checks: **296 passed, 10 browser opt-in skips**. The tests cover
populated and unknown flows, empty/unclosed fences, separate sources, mapped metadata,
exact file references versus unprovided neighbors, preservation of pending corrections,
and rejection of a multi-page batch before any page is promoted. Wheel build and
`git diff --check` pass. No new full-suite or browser result is claimed here.

[All retained outputs and sidecars](artifacts/wiki-improve-20260922/) distinguish
original execution outcomes from later revalidation. See the initial acceptance
report for running a fresh synthetic fixture; live commands spend model calls.

## Efficiency limits

| Run | Outcome at the time | Input tokens (cached included) | Output tokens | Seconds |
| --- | --- | --- | --- | --- |
| Original baseline | structurally accepted, quality revise | 270,878 | 3,552 | 157.85 |
| First improvement | accepted; decision/metadata defects found | 390,506 | 6,304 | 134.31 |
| Second improvement | rejected supplied-file citation; later revalidated | 349,863 | 4,769 | 104.46 |
| Unstaged correction | completed but destroyed page structure | 363,173 | 5,339 | 115.7 |
| First staged correction | rejected missing reference propagation | 485,182 | 3,958 | 93.8 |

These are cumulative provider counters, not unique evidence size. Replays and review
are additional cost; lower latency in one sample is not evidence of an overall
speedup or cost saving. The correctness safeguards are the purpose of this change.

## Final live results and independent review

The preserved correction succeeded on retry with the source-reference fix:
314,648 input tokens (261,888 cached),
3,386 output tokens, 80.3 seconds. It retains Mira's
ownership, the dated pilot decision and rationale, both diagrams, canonical
sections, individual file citations and mapped counts/dates. Repeated sync returns
`no_change` with zero model calls; the previously failed correction was not lost.

The blinded GPT-5.5 evaluator returned revise for the original baseline and accept
for the improved investigation, preferring the improved version. It also accepted
the corrected page with its additional evidence; that is a separate scenario,
not a same-input A/B comparison. The exact input-material hash matches for A/B.

Implementer review is stricter on one remaining sentence: “hosted work is deferred
until after the local pilot” adds an ordering not explicitly recorded in the source.
The source establishes the current local pilot and that hosting is not permanently
rejected, but no future schedule. This remains a wording follow-up; the raw model
output and the evaluator's acceptance are both retained rather than silently edited
or presented as universal factual correctness. The core correction/structure checks
pass, while semantic timing claims still need review.

The code now prevents the observed structural corruption and preserves retryable
work. It does not automatically prove decision rationale, timing, ownership or
source entailment. No cheaper-generation claim is made: retries and independent
review add to the token costs above. Remaining live coverage includes other entity
types and large-evidence extraction.
