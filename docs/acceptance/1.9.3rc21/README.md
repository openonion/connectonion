# REM native scheduling acceptance — 1.9.3rc21

The implementation base was reviewed maincb872f23 (rc17). The final base includes reviewed main332132b8 (rc18 mailbox CLI); the native
scheduling delta remains separate. Runtime dependency floors and stable1.9.2 remain.

## Actual desktop acceptance

Codex desktop 26.924.22138 adopted a CLI-written local legacy automation file.
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
85 minutes. A supported SIGINT preserved completed work and exited130. A native
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

Final candidate runtime source`dc91cbe28bdd85a0c14f0f88a85251c9f2858071` also passed the genuine native timer/CLI trial, recorded`no_change` and auto-archived. See [the sanitized execution receipt](native-execution.json).

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

The native prototype initially used the rc19 candidate number. A
parallel email release took rc19 before this PR merged; the native release is
rc21. Runtime receipts retain their exact source commit and trial timing.

## Final ledger

- Real native marker runs:3 archived. Actual native REM CLI passes:2 completed
  with`no_change` and auto-archived, including final runtime source dc91cbe2.
- Production native clock triggered19:01:57Sydney; its maintenance was still
  running at this checkpoint. Old launchd remains unloaded.
- Related regression:256 passed plus a sibling-docs discovery failure, followed
  by all 38 version/provider checks passing with the prepared docs checkout.
- Final CLI/handoff/history/native selection:223 passed. The first full CI found
  11 failures from three release/test-integration omissions; these were fixed,
  and the final PR must rerun the entire required matrix. None is waived.
- Local Mac 3.14 broad run was interrupted after 1534 passed and4 failures during
  disk pressure. Three passed on recheck; terminal-colour output also fails on
  unmodified rc18 baseline. This is not a full local-suite pass.
- All-extras locked dependency audit: no known vulnerabilities. Exact local
  package validation is separate from Trusted Publishing and public hashes.
- Docs source checks, lint (0 errors; inherited warnings), TypeScript, production
  build and generated blog/feed/sitemap checks passed. Actual screenshots and
  [independent review/rechecks](review.md) record limited presentation coverage.
- [PR2663](https://github.com/openonion/connectonion/pull/2663) holds final required
  checks. Publication uses its reviewed merge commit and immutable version tag.
  The exact-tag release workflow verifies public wheel/sdist hashes and creates
  the prerelease. This record was prepared before that publication completes.

## Long execution completion boundary

The first production wrapper reported the CLI was still active, with no final
exit status, and then archived. Its first maintenance batch made progress, but
full command completion was not established. The wrapper prompt now explicitly
requires polling the same session until an actual final exit status, including
hour-long maintenance; it must not end or kill the process merely to finish.

A real native timer then ran a controlled180-second blocking process. It stayed
IN_PROGRESS while running; the finish marker appeared before PENDING_REVIEW and
ARCHIVED. Independent epoch comparison confirms archive metadata followed the
finish marker. See [the precise receipt](native-long-wait.json). This is a
three-minute lifecycle test, not a claim that an hour-long production round has
been fully accepted. The live production definition received the same waiting
instruction without changing its ID, saved times or served-slot history.

During final integration, reviewed email PR2668 published/reserved rc20. Native scheduling therefore ships as rc21, inheriting that mailbox fix and preserving rc20 unchanged. Earlier runtime trials used the previously named prototype; they are not claimed as runs of the final public artifact.

The merged rc21 scheduler, version, handoff, REM CLI and email setup selection passed178tests. Final docs built654routes and passed blog discovery plus472-page SEO checks; lint reported0errors and155inherited warnings. Five rc21 production captures use docs source86169ca9. Final required CI and public artifact checks remain publication gates.
