# Proposed 1.9.3rc17 — backend maintenance and manual trial

**Preparation record. At this checkpoint the public/installed baseline was
1.9.3rc16.** A tag, package, release, new install or real-data trial is not proved
by this draft. Gate results will be recorded against the final source below.

## Why an installable preview is useful

The owner wants to test the latest package manually. The proposed preview would
make the already reviewed feedback fallback and inherited-claim audit corrections
available in an immutable package for that trial. Reading an old generated page
cannot establish what current generation does. A package makes that distinction
reproducible without claiming that the trial has already succeeded.

## Entire proposed scope

Relative to immutable rc16 source01f1f992, the preparation base is merged
main3a75894c5abba6aa068ecd09d30c13155ac22ca5. Its tree equals reviewed
57ae9503dafe336bbbeec838439ccea71ccc48f3 (58c88676f86f9f4f757f6e6e9cb90cfd04fe7ee9).
The full delta includes:

- #2621: eligible attributed feedback can reach a target when there is no new raw
  material, within one bounded maintenance turn; snapshot checks and per-target
  acceptance receipts preserve pending work on refusal or stale selection.
- #2640: inherited-claim exemptions require unchanged complete context and source
  identity, and deferred findings remain insufficient rather than a factual pass.
- #2653: tool recovery hints retain supplied argument names faithfully.
- #2658: test-only retry-delay recording, merged after all24sourcechecks passed;
  matching docs298 merged after all4checks passed.

The base delta was inspected again after that merge. The reader HTML,
CSS, layout, source popup and focus behavior are unchanged by this scope. Future
page content, audit decisions, log fields and terminal diagnostics can change.
A backend visual exemption must say that explicitly and receive independent
review. A passing manifest parser alone does not justify the exemption.

Pending reader/navigation/source/translation/accounting candidates, including
#2655 and #2657, retain their own native acceptance gates. They are outside this
proposed package. This record does not authorize importing them under the backend
exemption.

## Manual trial after publication — not executed

Pick a page with a specific, genuinely wrong statement and retain its before text
privately. The owner supplies a correction with its actual author and basis using
`co rem reflect PAGE STATEMENT --kind correction --author NAME --basis TEXT`.
Use `--previous` when identifying the wrong wording is useful. A reflection records
an attributed assertion; it is not proof of truth or permission to overwrite facts.

On the owner's next explicitly chosen investigation of that page, check the
recorded inputs and result. If there is no new original-source material, expect
`mode: feedback_only`, zero raw items and explicit feedback attribution. A normal
raw-material run is not evidence of the empty-raw path. An unavailable provider
is also different from a healthy source with no new material.

The correction should either yield a source-supported accepted page or remain
pending with an explained refusal/deferment. A changed file, completed model
wrapper or receipt alone does not prove the correction is true. An accepted
no-change decision must refer to the selected unchanged snapshot; repeat pending
processing must not silently acknowledge an unaccepted target. Race/crash cases
are deterministic isolated regression evidence, not a claim the owner reproduced
a race in a real notebook.

For inherited claims, check one consequential qualified statement against its
exact adjacent original. The useful result preserves or corrects its conditions,
attribution, time and source; dropping a condition is not unchanged prose. Old
content deferred by preservation policy must not acquire a factual PASS merely
because it was kept. Distinguish a narrow represented affiliation from employment
or contracting identity, and conditional support guidance from demonstrated
completion. Current saved-page examples do not prove a current-model regression;
the historic dispatch packet was not established.

For the resulting page, the owner can check whether the first useful finding is
clear, related context is reachable and the adjacent original supports the claim.
Capture desktop/phone, privacy and keyboard states only through permitted manual
review; none has been supplied for this candidate. Keep private identities,
originals and screenshots out of public issues. A de-identified issue should name
the failed expectation, source/packet availability, outcome and reproducible scope.

This scoped trial does not replace the requested first-run acceptance: all
historical real contacts/projects, the owner page, night maintenance, morning
recall, supported useful connections and current desktop/phone/accessibility
remain separate requirements. No automatic init, mailbox scan, model call,
scheduler run/restart, real notebook rewrite or screenshot workaround is part of
this preparation.

## Release gate ledger — pending

- Exact merged source scope, dependency/forward-port state and reviewed exemption.
- Version/lock/handoff metadata, release notes/index and candidate journal wording.
- Full final offline suite, dependency audit, clean build, Twine validation,
  isolated installed-wheel acceptance and independent final review.
- Version PR CI, normal merge, immutable tag and pinned release workflow.
- Trusted Publishing, public byte equality, GitHub prerelease, stable unchanged,
  exact-pin installation in both existing runtimes without active-work restart.
- After public availability: docs sync from the tag and canonical content checks.

Product usefulness, source truth, current-model behavior, real first-run/night
maintenance and native UI acceptance remain unverified. Do not mark the REM goal
or broader correction/design issues complete from this preparation.
