# Carried finding continuity — candidate, 22 October 2026

Original base main e9bc54d1285d104715bcfa62b985f0f4cd5b8191; issue #2639.
The initial installed-CLI observation used rc12. After the main integration below,
the latest public preview rc13 was verified against its immutable tag and official
package hashes, then installed in both the CLI and scheduled Python environment.
Its actual CLI interpreter, inspected outside this checkout, still has the old
whitespace-erasing/global-substring exemption. This candidate is not in rc13.

## Source failure and chosen boundary

Nine initial review-level negatives failed; three unchanged-context controls
passed. Word changes, removed conditions, swapped originals, History/current
movement, headings/code examples and duplicate occurrences could all be declared
carried content and convert a model FAIL to PASS. Independent AI source review
found two further gaps in the first repair: citation offsets were discarded and
H1 excluded. Two additional red tests reproduced these. Two adjacent-qualification
regressions then showed why removing a separate paragraph/bullet must invalidate
its section's exemption too.

The candidate preserves meaningful spaces, complete old prose contexts, title and
section paths, ordered cited original identities and their normalized relative
positions. Every occurrence must be covered. The old contexts must survive in
order within their section; missing/ambiguous bindings do not qualify. Unmatched
rewrites get ordinary review. Intact old blocks may remain alongside additions.
Deferred old findings are insufficient, never a factual pass, with a count in the
saved promotion review. Ordinary active failures still refuse a changed candidate
and preserve the synthetic accepted notebook.

## Evidence limits and gates

Initial strict block matching produced five existing-test failures: three concerned
incomplete H1/citation fixtures, two showed intact old prose must remain protectable
when a new sentence is appended. The implementation now tracks unchanged complete
old spans; fixtures use actual source definitions and stable citation placement.
Prior contract tests retain checks of unchanged content and repair behavior.
Final related/full results and independent exact-head source/copy review follow in
the PR. No regression count here is a claim of model semantic compliance.

All new source examples are invented. No real mail/model/init/provider collection,
scheduler restart, notebook/archive write or screenshot/browser workaround. This
is syntactic continuity, not proof of old truth or equivalent meaning in all
surrounding discourse. Actual model and native desktop/phone/privacy/focus/
accessibility acceptance remain pending. Security/compatibility and exact-head CI
remain mandatory; no advisory waiver, Python minimum change, version bump, merge,
tag or publication. Other unmerged source candidates are not integrated.

A later exact-head review found inconsistent verdict/finding pairs could still
produce a factual PASS: PASS with a deferred finding, or PASS/INSUFFICIENT with
an active finding. Three actual promotion regressions failed before normalizing
active findings to FAIL and deferred-only findings to INSUFFICIENT independently
of the top-level model label. The initial full run on the preceding source head
is retained separately; a fresh complete run verifies the final correction.

## Integration after main advanced

Main bdc8c4316a0e4b1d47e14cd222ebc08b0ea61bb0 merged the separately reviewed
Codex-history and security repair #2627, including its Python3.11 minimum and
patched dependency floors. This candidate merges that actual main without
rewriting published commits; both appended CLI sections are retained. Prior
Pillow/pypdf failures describe the old base, not a current audit of this merged
candidate. The fresh frozen Python3.11 environment has patched Pillow13.0.0,
pypdf6.21.2 and cryptography50.0.2; its exact-lock audit found no known advisories.
Public rc13 tag points to bdc8c43 and its release workflow39750719191 passed all
jobs. Both installed Python environments import rc13 and pass dependency checks;
the existing co wrapper hash is unchanged. No scheduler or model run was started.
Fresh regression/security/exact-head results are recorded in the PR; no native,
model, scheduling-migration or publication of this candidate is inferred.

The first full regression after integration used a fresh uv environment without
pip and failed six tests: one CLI driver prerequisite and five clock-sensitive
fixtures. The project fixtures capture NOW at module import; Calendar expiry is
only an hour after collection. Tool-clock observations crossed multiple hours
during the run. Pip was added as a test tool; all six isolated cases then passed
without source changes. The failed full run is retained separately from the next
fresh full result; no failure was waived or replaced by an isolated-only claim.
The CLI transport case mocks send; it is not native browser/page acceptance.
