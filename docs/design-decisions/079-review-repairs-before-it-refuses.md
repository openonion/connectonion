# Review repairs before it refuses; what it cannot repair it removes

Status: implemented on branch `rem/init-quality` (2026-10-15), not yet released.
How it behaves: `docs/cli/rem.md`, "Review before a page is saved".

## The problem

A model-written page is paid for before review sees it. Review used to have two
answers, accept or refuse, and only project investigations had repair turns. On
1.9.2b3's first run (2026-10-10) that lost whole pages for small faults:

- callum-reid was refused on every pass for one heading glued to the end
  of a paragraph ("… [10]. ## Our relationship").
- job-followup's skill page was refused for citing its applications log as a
  hash-pinned `file:` id, which only project pages accepted.
- A Callum History line was refused whole because the audit copied one claim
  without its `[7]`, though the line's first sentence was true.

Meanwhile the checks that mattered most were missing: 8 of 89 quotes on that
notebook were not in their source, and the cited-claim audit ran only on project
investigations, while person pages are where a wrong claim is acted on.

## Decision

1. **Check more.** Every `“…”` on a person, organisation or project page must be
   word for word in a source its line cites. The cited-claim audit runs on every
   write of those pages, reads the turn's own material, fits a large packet by
   shortening excerpts evenly, and names each failing claim.
2. **Repair before refusing.** Every page type gets two repair turns naming what
   review refused and where the originals are. A page someone else changed
   meanwhile gets none.
3. **Remove only what is refuted.** When every remaining error is a citation, a
   misquote or an audit finding, the sentence holding each goes (a contact
   field says `Unknown`) and the rest is saved. `review.json` says how many
   claims went. Any other error still refuses the page.
4. **Let code settle what code can.** Duplicate or glued sections are merged;
   each source is listed once and dated from its original; every turn is told
   today's date.
5. **An audit that cannot judge is not a refusal.** `INSUFFICIENT` is recorded;
   nobody has shown those claims to be wrong.

## Why not refuse and retry later

A refusal re-reads the same material on the next run at full cost, and the
writer, not told what failed, makes the same page. The repair turn costs a
fraction of the page and is told exactly what to fix. What cannot be fixed is a
named sentence, not the page around it: a page with one refuted sentence and
twenty sound ones is better kept without that sentence than lost.

## Limits

Removal is only as good as the audit's findings: an unflagged wrong claim
stays. A quote whose original is not held, or is truncated, is left to the
audit, not judged. Every refused page now goes into one ledger and is retried
once a day, three times at most on the same material (`docs/cli/rem.md`,
"Refused pages and the daily round").
