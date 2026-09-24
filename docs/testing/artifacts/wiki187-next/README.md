# Atlas comparison: single-page update and quality review

Decision: accept this synthetic case after the citation fix and deterministic
revalidation. This is one case, not a general model or Skill ranking.

## Fixed goal and evidence

Explain the local word counter, show the command and sample result, preserve the
unimplemented hosted-site request, and retain ownership/coverage limits and
traceable sources. Both generations used GPT-5.6-Luna and identical canonical
material (SHA-256 `611c6f0181ecba14fabf98662a723c12363f2c959e4d45aa8dc6e939f70c83b9`).
External fixture files were unchanged. Both original tool histories contain the
command `python3 count.py draft.txt` and returned `3`; relevant matched events,
without reasoning traces or unrelated history, are in [review-request.json](review-request.json).

## What failed and what changed

The first shorter candidate used unsupported `[S1]` citations and bundled source
files. It was rejected without replacing the live page; retain
[its output](rejected-first-candidate.md) and [metrics](rejected-first-result.json).
The shared investigation Skill now carries the evidence format independently of
person/project templates. A second generation used numbered, separate sources.

The second candidate was initially rejected because its citation to the exact
supplied existing page was not recognized. The checker now recognizes explicitly
labelled prior-page context only when that page was supplied. This does not make
retained metadata independent corroboration. Positive and negative regression
cases cover that distinction. [Revalidation](revalidation.json) promoted this
retained candidate in a fresh synthetic notebook without another model call.
The original [failed result](candidate-result.json) remains unchanged. The last
Skill paragraph clarifying prior-page context was added after this generation;
it has deterministic test coverage but has not had another live generation.

## Independent review and verification

A blinded GPT-5.5 evaluator first received source contents without original
execution records and flagged both execution claims. We checked the original
matched tool calls/responses and found the commands had actually run. The defect
was in the evaluator's evidence bundle, not fabricated execution. Both
[first review](review-incomplete-evidence.json) and
[review after adding those records](review-complete-evidence.json) are retained.
The corrected review gives both pages 2/2 on six criteria, no blockers, and
slightly prefers B for clearer uncertainty and concise wording. Implementer
review confirms local-only scope, per-file references, actual output, unknown
ownership and retained open hosting work. Existing-page session/date metadata
remains derived context. No judge verdict automatically updates executable Skills.

An earlier Astra evaluator attempt was rejected by the local CLI/backend as
unsupported; no CLI upgrade was made. Evaluator identity, usage, and fallback are
retained in [evaluator-runs.json](evaluator-runs.json). Missing evidence should
produce insufficient evidence rather than a confident fabrication verdict.

## Efficiency after quality

| Measurement | A: baseline | B: second candidate |
| --- | --- | --- |
| Instructions, characters | 51,219 | 21,705 |
| Material, characters | 1,969 | 1,969 |
| Cumulative input tokens | 752,276 | 311,207 |
| Cached input tokens, included above | 688,128 | 278,272 |
| Output tokens | 7,342 | 4,381 |
| Elapsed seconds | not recorded | 103.53 |

B used about 59% fewer input tokens in this case. This comparison excludes the
rejected first retry (243,122 input / 3,236 output) and evaluator overhead; those
are retained separately and must be included in total experiment cost. No dollar
cost or speedup is claimed. The original [worksheet](comparison-worksheet.md)
remains pending by design; this reviewed report supplies the final decision.

Next: repeat on person and installed-Skill pages before making cross-entity
quality/efficiency claims, then resolve the corrections and budget contracts in
the main checklist. Do not rerun the historical queue based on this one result.
