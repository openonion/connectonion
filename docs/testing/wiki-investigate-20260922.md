# Investigation and update acceptance — 2026-09-22

Tested PR #1454 at `d45b72f4` in an isolated checkout. The existing integration
checkout had an unrelated reader edit and people-acceptance script; neither was
changed. Only synthetic Atlas evidence was sent to the model. No real mailbox,
background scheduler, historical queue or release was started.

## Results

- Wiki unit and CLI regression: **285 passed, 10 opt-in browser skips**, including
  the new acceptance-harness regression. Staged inquiry, reflection history,
  review decisions, capture deduplication, failure recovery and daily call limits
  are covered by deterministic tests; this does not certify their live quality.
- Live Luna investigation: candidate accepted and page promoted; 157.85 seconds,
  270,878 input tokens (237,568 cached), 3,552 output tokens.
- Live correction/maintenance: introduced a clearly labelled stale owner claim,
  then supplied an attributed correction and a synthetic ownership source. Sync
  changed Leo to Mira, retained the correction/date/source, and kept the project
  local and unlaunched. 66 seconds, 329,098 input tokens (290,560 cached), 2,847 output.
- Repeated sync: `no_change`, zero items, zero model calls, no changed pages.
- Wheel build and diff check pass. No full-suite or new browser run is claimed.

Counters are cumulative provider usage, not unique source size. No measured dollar
cost or performance comparison with earlier runs is claimed.

## Quality findings: investigation needs revision

The page describes the local word counter and leaves the hosted-site request
unimplemented. The sample command can be checked against the retained fixture.
Structural acceptance does **not** establish full acceptance:

1. `Overview` is prose rather than the required short fenced ASCII flow. The
   project template explicitly requests that flow; the current structural checker
   accepts its absence. Rendering/validation follow-up: add a project-specific
   acceptance check without requiring invented diagrams for genuinely unknown flows.
2. `Key decisions` says “Keep the tool local and command-line based.” The evidence
   establishes current behavior, not a recorded decision or its rationale.
   Synthesis follow-up: preserve it as implementation status and mark rationale
   unknown; test against a separate fixture that actually contains a dated decision.
3. Source [3] combines the input and output files despite the shared instruction
   asking for separately traceable files. Both paths exist, so this is a precision
   issue, not a claim that the files were fabricated.

The correction run preserves these pre-existing shortcomings. Passing the owner
correction case is not a claim that maintenance repairs all unrelated page defects.

## Harness defect fixed

The first live attempt did not call a model: the acceptance script put its
synthetic project under `/tmp`, which the newer project scanner intentionally
excludes, then indexed an empty project map. The harness now defaults to a fresh
subdirectory of the current workspace, rejects excluded paths with an actionable
message before fixture creation, checks for an empty map and retains structured
failure results when model investigation fails. The scanner exclusion is unchanged.

## Reproduce

Use the project environment with `co` on PATH and this checkout on PYTHONPATH.
Choose a new directory under a normal workspace, outside `/tmp`:

```sh
python scripts/validation/wiki_project_acceptance.py --directory /absolute/workspace/atlas-check --run-model
python docs/testing/artifacts/wiki-20260922/run-correction.py /absolute/workspace/atlas-check
python -m pytest tests/unit/test_wiki* tests/e2e/cli/test_wiki* -q
```

The first two commands deliberately spend model calls. The second disables live
subscriptions in the disposable fixture before foreground sync and refuses to
reuse a fixture that already contains correction evidence. Do not use it on a
personal Wiki. These runs used GPT-5.6-Luna; staged routing and large-evidence
extraction were not exercised live in this round.

[Retained pages, original material, fixture and metrics](artifacts/wiki-20260922/)
include the original candidate, stale test page, correction and updated result.
Remaining live coverage includes people/organization/Skill investigation, large
source extraction, conflicting corrections, and daily scheduling behavior.

## Independent review

A blinded GPT-5.5 review returned **revise**, independently identifying all three
quality findings above. It received the candidate, predefined goals, original
materials and fixture contents, without generator identity/cost. Its reasons and
evidence pointers were checked against the page. The generator's reported command
execution was identified as an assertion, not supplied as a verified tool transcript.
The reviewer did not treat absent execution logs as proof of fabrication.

[Review](artifacts/wiki-20260922/independent-review.json),
[request](artifacts/wiki-20260922/independent-request.json), and
[evaluator model/usage](artifacts/wiki-20260922/independent-execution.json) are retained.
This is one live project case and one correction, not a multi-model ranking.
