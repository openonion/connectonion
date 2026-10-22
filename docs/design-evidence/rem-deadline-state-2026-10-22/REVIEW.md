# Deadline and quiet-state boundary — candidate, 22 October 2026

Base main e9bc54d1285d104715bcfa62b985f0f4cd5b8191. Published/installed newest
preview remains 1.9.3rc12. Related existing issues #2464, #2207 and #2143;
no duplicate issue. Candidate not released or visually accepted.

## Confirmed source failures

- `_quiet` and reader `threads` classified an old request with due <= today as
  quiet. Active counts and the morning selection excluded it; an old request
  with a future deadline retained protection. Source fixtures reproduce both
  due-today and overdue demotion.
- The morning heading counted overdue records as “due soon.”
- Python date extraction missed English written deadlines that the reader used.
- Person synthesis combined matching-reply closure with automatic History after
  60 days of silence or a passed meeting date. This is a conflicting instruction;
  no claim is made that a new model run demonstrated its outcome.

## Chosen repair

Keep explicit deadlines out of age-only quiet classification, whether past,
today or future. Split overdue and upcoming counts, preserve existing source
links, privacy and local dismissal. Keep undated old context reviewable in its
existing disclosure and explain that grouping by recorded date is not resolution.
Remove age/meeting-only closure instructions, without converting an unanswered
request into an agreed debt or inventing a current priority assessment.

Match valid English written dates in Python and JS. Independent review found
impossible dates/leap rollover diverging because Python validated but JS did not;
three shared regressions failed before validating the reader's calendar too.
Existing omitted-year inference remains a known limitation; this is not proof
of a promised year. No new dependency, identity/relationship store or notebook
migration is introduced.

## Evidence and remaining gates

- Four initial regressions failed, one future-deadline control passed. A separate
  header expectation failed, and three written-date cases failed before repair.
- Tests inspect the actual person synthesis note dispatched through `run_rounds`
  with an offline runner. They do not simulate or establish real model reasoning.
- The broader first run had 421 passes/two old-contract failures (count and header);
  expectations were updated to the new due-state contract with boundary fixtures
  retained. Final related census/reader/investigation tests: **432 passed in
  26.20s**. Final full results follow in the PR.
- Real read-only notebook check: 587 visible pages, zero old explicit-deadline
  candidates by this parser, all page hashes unchanged. This limits the real-data
  evidence; no claim that real obligations were repaired.
- Independent exact-head review, current native desktop/phone, actual keyboard/focus,
  accessibility, real provider/model/init acceptance and release gates remain open.
  No browser/renderer/screenshot workaround, provider call or notebook write.
- Dependency security/compatibility gates remain required. No Python minimum change,
  advisory waiver, version bump, merge, tag or publication.
