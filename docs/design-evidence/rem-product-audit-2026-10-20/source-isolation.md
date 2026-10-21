# Source failure isolation — issue #2617

## Evidence and scope

Read-only installed rc12 status contained a failed Gmail sync with zero model
attempts. No real source, auth, init, scheduler, browser or model was run. The
observed failure does not establish whether another source had pending material.

The initial one-case red fixture omitted consent on its healthy source and alone
was insufficient evidence. Corrected regressions use the real approved Codex
subscription including consent and since, and fail against baseline e9bc54d:
2 failed,5 deselected in0.45s. Both Gmail and Outlook failure variants stop before
the available consented session. Baseline source was restored in the isolated
checkout for this test, then the candidate source restored in a finally block.

The candidate continues only existing selected subscriptions after the same caught
collection exceptions, records sanitized source failures, and preserves failed
checkpoints. It reports partial after healthy acceptance, failed without material,
and stops --all on either; no extra model attempt is reserved for a collection
failure. Disabled sources remain filtered by the real selection helper. Native
page acceptance and trusted custom callback boundaries are unchanged.

## Verification

- Related service, daily, collection-failure and new isolation suite:123 passed
  in4.95s. Includes available mailbox/local after unavailable mailbox, repeated
  ticks, all unavailable, bounded --all, disabled source exclusion, sanitized
  unexpected-error text, scheduled attention and explicit CLI nonzero results.
- First full offline run: 3 failed, 16,977 passed, 334 skipped, 7 warnings in
  251.00s. Failures: Google Calendar fixture's cached expiry and two people-page
  collection-time date windows. Calendar/people files rerun fresh: 57 passed in
  2.52s. Their module-level FUTURE_EXPIRY/NOW crossed a machine wall-clock/date
  jump; no source change or test exemption was used. Fresh full rerun: 16,979 passed, 335 skipped, 7 warnings in 339.14s.
  The first full is not claimed green. Browser/real API opt-ins remain skipped.
- Independent AI source review found no blockers in the candidate; exact committed head
  `93bb2e91c3cc2e44b189e96b34c19df47588e926` was approved; remote CI remains
  required. Its lockfile audit currently fails on Pillow advisories; no waiver. No real human founder review.
- No before/after screenshot: this is orchestration/status behavior; current local
  preview browser access remains unavailable. No visual acceptance claim.
- Real overnight/provider recovery and semantic page quality remain unverified.

A successful batch covers the attempted source and its accepted material, not all
subscription history. A later batch can rotate before encountering an unavailable
source; retained run history describes the earlier observed failure. No source
health certification, automatic reauthentication, generic queue or extra retry loop
is introduced.
