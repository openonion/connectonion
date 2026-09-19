# Comparing Wiki output quality

Fix the intended outcome before generating candidates. For the Atlas fixture:
explain the local word counter to a new reader; provide the real command and
sample result; preserve the unimplemented hosting request; identify evidence,
missing ownership and limits; use the canonical page shape.

Keep the source material, external fixture-file contents, starting page, model,
harness and input window fixed when measuring a prompt/code change. When comparing
models, keep the other inputs fixed and record the changed model. Save both
outputs, including failures. A single pair is a diagnostic case, not a general
model ranking or estimated success rate.

Run `scripts/validation/wiki_compare_outputs.py BEFORE_TASK AFTER_TASK` to prepare
a comparison worksheet. It checks canonical material hashes and reports actual
available usage; missing measurements remain unknown. It does not award a quality
score or automatically prefer cheaper output.

## Independent model review

Use a separately configured capable evaluator to examine anonymized A/B outputs
against the original evidence and predefined goals. Withhold model identities and
costs until the quality review is complete, so efficiency cannot compensate for an
unsupported completion claim. Record the evaluator's model and outcome. Never
silently route private/local-only sources to a cloud evaluator.

The evaluator returns a concise evidence-based assessment, not private reasoning
traces. For each criterion, use 0 (misses it/material error), 1 (partial/minor
problem), or 2 (meets it), with a short reason and precise source/output pointer:

- Goal achievement and usefulness for the intended reader.
- Factual support, including distinctions between intent, execution and quality.
- Important coverage and omissions.
- Citation traceability to retained evidence.
- Uncertainty, timing, conflicts and missing information.
- Readability and actionable entry points.

Fabricated delivery, materially contradicted facts, and fabricated sources are
blocking failures, regardless of total score. The evaluator may return a tie or
insufficient evidence. Human/implementer review verifies its concrete findings;
a stronger model is not a ground-truth oracle. Report quality first, then compare
latency, retries, input/output/cache tokens and measured cost where available.

## Follow-up loop

Every comparison records accept/revise/insufficient evidence. A defect entry
names the observed problem, evidence, suspected stage (collection/extraction/
synthesis/rendering), proposed correction and regression case. Distinguish a
suspected cause from a verified diagnosis. Retain the rejected result and rerun
the same case after a targeted fix. Never improve a score by weakening the
predefined goal or suppressing contradictory evidence.

Do not start an unbounded retry loop. Escalation or more source retrieval needs a
specific reason and a bounded next run. Method improvements remain proposals
until checked against the failing example and a counterexample; do not rewrite
executable skills automatically from one evaluator's opinion. See #1610/#1611.

## Repeating the retained synthetic review

The [Atlas review request](artifacts/wiki187-next/review-request.json) retains
anonymized outputs, original materials, inspected fixture contents and matched
command/output evidence from each generator run. Supply all four evidence kinds:
source files alone cannot establish what the generator actually executed.
Missing execution logs mean insufficient evidence, not proven fabrication.

For an explicit live review, copy that request to a disposable directory and run
`co ai --json --harness codex --model gpt-5.5 --sandbox workspace-write` with a
prompt to read it, apply the six criteria above and write a new review JSON.
This is opt-in model execution, outside the deterministic pytest suite. Preserve
the returned usage and evaluator identity separately from the blinded request.
No raw internal reasoning or unrelated session history belongs in the evidence
bundle. A model/backend compatibility failure is a failed attempt; record any
explicit fallback and never silently upgrade the user's CLI.

For a colleague's PR, retain original authorship and route changes to their
design intent or disputed ownership back to the original author. Record the
concrete proposed change and evidence before requesting that decision.
