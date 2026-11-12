# rc27 preparation and bounded manual recheck

This is a dated candidate record, not public availability or product maturity.
Baseline public rc26: `87d9bac2768b39b4c5404e8cd32f3c1c57a672a5`. Normal source merges:
#2699 a7ef418765e462dff5579d058f0ca6e748a0f8be and #2694
7e2ad605b7286b0bbe2b0ae74dbab806f6f09f98. The final merged tree
ce7d7bd6509d259bf6e948286880d48f14abf417 equals the independently reviewed
local rehearsal d426964363d9e14c01baf64481ab81c4d2e3b210, which passed 17,655 offline
tests / 336 skipped / 1,170 warnings in 125.48 seconds. Source code beyond these two reviewed
repairs must be reassessed; metadata/artifact gates are still separate.

## What was actually reproduced

The quote suite initially reported 8 failed and 15 passed; a placeholder-binding control
also failed before correction. Independent review found source targets truncated
at spaces and definitions accepted from later sections: 3 additional red controls
preceded the full-target/section-boundary correction. Relevant suites passed 554 tests.
A private saved candidate/current-page comparison is consistent with recorded
restoration; the exact promotion postimage and absence of later edits were not
established. Candidate-authored duplicate obligations remain distinct.

The rc26+quote integration initially failed the unchanged Claude process-start
marker test. The unchanged rc26 control also missed the marker; its first
invocation additionally used the wrong checkout cwd and had isolation teardown
errors. A local loopback getfqdn probe took 35.006 seconds. The separate startup
repair's DNS/auth/cleanup controls failed 1 test before correction, then 128 related
bridge/interruption/tool tests passed in 14.33 seconds with the same deadlines/late-write
assertions. The combined full result above passed after both repairs. Failed
attempts were not counted as acceptance or hidden by skips/timeouts.

## Remaining release gates

Version/lock/handoff consistency; reviewed complete backend exemption; strict
all-extras frozen dependency audit; clean build/Twine; isolated installed-wheel
checks; independent final metadata/artifact review; exact-head version-PR CI;
normal merge/fresh immutable tag and Trusted Publishing; public artifact byte
comparison/GitHub prerelease/stable unchanged; exact-pin installation; docs tag
sync only after matching public availability. Record final results in the
associated PR/workflow, rather than inferring them from this preparation ledger.

## Manual product recheck after publication — not executed

For a deliberately selected future page update, compare before/candidate/promoted
bytes privately: a literal quote extended by punctuation should not restore a
second whole sentence when its immediately bound originals are unchanged. A real
lost qualifier/source must remain protected. Introductory evidence must stay
introductory. Separately inspect any duplication already authored in the candidate.
The page's claim must still be checked against its exact adjacent original.
Installing a package does not rewrite old pages.

For an operator-chosen Claude trial, verify receiver startup, normal approval,
interruption and absence of a late write; avoid treating one local DNS observation
as a timing guarantee. No actual provider/model trial was performed here. Offline
package probes may initialize synthetic temporary HOME directories with external
runtime connections blocked; they are not a real REM initialization or account trial.

Current real notebook desktop/phone/source-popup/privacy/focus/accessibility,
all historical people/projects, useful first insight, overnight correctness and
morning recall remain unproved. No source collection, real notebook/cache rewrite,
scheduler start/restart, credentials/account change or alternative renderer is
part of preparation. Do not close the broader REM maturity goal from these gates.
