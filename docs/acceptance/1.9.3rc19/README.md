# REM native scheduling acceptance — 1.9.3rc19

The implementation base was reviewed maincb872f23 (rc17). Preview rc19 avoids
concurrent rc18 mailbox work. Runtime dependency floors and stable1.9.2 remain.

## Actual desktop acceptance

Codex desktop26.924.22138 adopted a CLI-written local legacy automation file.
Three real scheduled model turns invoked an isolated marker script; all three
native threads archived automatically. No manual marker execution or database
registration insertion was used. A cold pending run spent about ten minutes
waiting for startup/plugin reconciliation; warm executions followed. Disk
pressure affected trial setup too, so causal attribution to one recovery step
is not claimed. Original seven task definitions were restored byte-for-byte.

A separate task written by the new provider used its actual daily wall-clock
rule. Codex triggered the pinned Python/REM CLI, which completed scheduled sync
with`no_change` against a notebook with all body-source subscriptions disabled.
The native wrapper then archived and the trial task was paused. This validates
the real scheduling/CLI/slot path; it is not a useful-findings or mailbox trial.

The owner's existing 17:00 batch was still scanning historical sessions after
85minutes. A supported SIGINT preserved completed work and exited130. A native
PAUSED task had already been adopted. Handoff then verified launchd unloaded,
activated native scheduling and preserved last-served-slot history. Read-only
verification subsequently confirmed native ACTIVE adoption and a next19:01slot.
That next production pass is not claimed complete by the isolated trial.

The installed native timezone branch miscalculated explicit TZID offsets.
Actual native calculations verified the local-clock path, DST gap/first-fold
behavior and selected hour/minute pairs. Mismatched saved/computer zones retain
launchd with a visible note. No native database writes or caller-authentication
bypass is part of the adapter.

## Regression and failure checks

Targeted scheduler/service/first-run regression passed195tests before final
review fixes. Final results, full offline checks, lock audit, exact wheel/sdist
validation, PR CI, immutable-tag publishing and installed-version checks are
recorded in the final ledger. Earlier failed tool-install/build attempts caused
by full disk do not count as passing validation.

An independent AI reviewer in a technology-founder/marketing/UI role found
cutover locking, failed unload, failed replacement and changed-time status issues.
The implementation adds those checks and corresponding regression cases. This
is an AI role review, not a claim that a human founder participated.

## Presentation and remaining gaps

CLI output and the rendered documentation flows are reviewed separately from
native execution. Native computer APIs are disabled, so the Scheduled form,
native run details/recent-project arrangement and remote desktop project flow
were not visually inspected. Sleep/wake and an overnight production pass remain
unverified. There is no all-page, source-quality or useful-recall pass claimed.

## Final ledger

Pending final source revision and publication verification.
