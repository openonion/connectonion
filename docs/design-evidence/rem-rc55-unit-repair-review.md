# rc55 unit repair review

The runtime Skills `connectonion/useful_skills/rem-investigate/SKILL.md`,
`rem-investigate-person/SKILL.md`, `rem-page-person/SKILL.md`,
`rem-owner-page/SKILL.md`, `rem-maintain/SKILL.md` and
`rem-page-project/SKILL.md` were condensed to restore the complete one-page
instruction budget to 15,000 characters. This document is maintenance evidence,
not runtime instructions.

The person investigation carries 14,930 characters; the owner investigation
carries 14,916. All four page kinds fit for investigation and maintenance.
Quote-first evidence, source capture, ownership attribution, agreed debts,
booking-display timezone boundaries and work-only owner insights remain.

The archive regression test encoded the superseded eager-download behavior.
It now checks selective attachment metadata indexing and refuses downloads
during gathering. The HTTP timeout regression was a dictionary named
`requests`, not an unbounded HTTP operation; renaming it to `pending` preserves
translation-queue behavior and the unchanged timeout check.

## Independent CLI experience review

A separate AI reviewer used a marketing/UI technology-founder perspective.
This was an AI role review, not a human founder review. It inspected actual
plain and color-enabled terminal help for:

- `co browser history --help`
- `co browser import --help`
- `co rem --help`
- `co rem exec --help`

The review covered these eight CLI states and their handlers/diff, not browser
pages, mobile layouts or all commands. It found no significant issues: history
states read-only behavior, macOS scope, filters and defaults; import explains
cookie writes, Keychain handling, billed sessions and dry-run; REM exposes exec;
exec names its model runner, writes and scheduled gating. Examples and Back
navigation are visibly styled in terminals, with plain words preserved in pipes.
Recheck these states when changing their purpose, effects, options or rendering.

The five originally failing files pass (160 tests total); adjacent REM source,
muse and attachment checks pass (155 tests). The expanded affected-file run passes 680 tests, including the original four
fast files and all six wording assertions identified during the full run; the
help-contract file passes its two tests.

The single full-suite run used CLT git, Python 3.13 and eight worksteal workers.
It recorded 188 failed, 17,793 passed, 20 skipped, 2,757 warnings and 6 errors
in 111.95 seconds before the six wording assertions were repaired. Numerous
failures are sandbox-specific: denied socket/process operations, writes outside
permitted roots and handoff commands that explicitly refuse sandbox execution.
The session cannot escalate outside the sandbox. This is not a clean full-suite
verification; an unrestricted rerun remains necessary. The full run was not repeated.
