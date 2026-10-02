# The writer could not read the code

**Design Journal draft.** This describes a candidate in draft PR #2141, not a
released package or a published docs-site article.

A project page asked its reader to verify the latest branch before relying on
it. The initial writer had a README, package metadata and Git dates. Its prompt
also prohibited opening any other file. More model time could not reveal the
implementation that the task kept outside the evidence.

In the inspected fixed revision, a PDF app's download link had no corresponding
handler. Its CLI used a separate renderer. The config loader could select bundled
example data when no explicit config variable was set and both JSON candidates
in the current directory were absent.
The three PDF fixture cases bypassed that loader and the CLI wrapper. These were
useful source findings; none proved an observed runtime error or a test outcome.

Keeping the metadata-only packet was cheap, but preserved the discovery gap.
Putting all source into the initial prompt would make every page pay for files
it did not need. Allowing an unrestricted checkout search would reopen mutable
files and make evidence harder to reproduce.

The candidate instead supplies a fixed tracked tree and an index of at most
60 eligible text snapshots. The agent searches relevant supplied files with their
context. Size and path exclusions are explicit, and an omitted body does not
mean missing implementation. Accepted citations retain the supplied original.

This trades a small initial index for additional, variable source reads. The cost
estimate says so; the quota guard remains in place. It also leaves real limits:
60 files cannot cover every repository, and the reader's short source prefix may
stop before the decisive clause.

The real page was manually corrected and independently reviewed. The related
unit and browser checks pass. A live automatic first write and all-page semantic
review remain unverified. The next question is whether the writer uses this access
to produce supported findings, rather than another list of verification requests.

See the [review and exact coverage](../../design-evidence/rem-initial-project-source-review-2026-10-03/REVIEW.md).
