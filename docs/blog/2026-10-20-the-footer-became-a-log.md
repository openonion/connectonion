# The footer became a log

This implementation is included in the 1.9.3rc8 candidate. Its [release notes](../releases/1.9.3rc8.md) distinguish publication and remaining acceptance work.

One REM page ended with the same investigation status, again and again. A pass had finished, so the runner appended another date. The next pass did the same. The line meant to answer “has this page been investigated?” was accumulating the history of every attempt.

The report was already in #1988. A fresh read-only inspection found eleven saved pages with repeated pass kinds. It was tempting to remove duplicate strings, but that would keep both yesterday’s investigation and today’s. The summary would keep growing. We needed to decide what the line was for.

The footer now keeps the latest dated pass of each known kind. Mapping, writing, investigation and enrichment remain distinct. Run details stay in their existing records; the page keeps its sourced content. An older date appended later cannot replace a newer dated status.

Review found a hole in that rule. The first implementation treated any dated fragment as a pass, which could collapse two custom provenance notes. A failing test made the loss visible. Restricting recognition to the four known operations preserves those unfamiliar notes.

The operational queue reads the latest investigation or writing date, so shortening the footer must preserve that date. That boundary is tested alongside fifty repeated passes and unchanged prose. The old unfinished-list count remains a count of visible stamps, not a claim about lifetime work.

This fixes the accumulating status line on the next successful pass. It does not shorten an article, verify its claims, or make an old page current. Those are separate problems in the same issue. A tidy footer should make the state easier to read without making the notebook sound more certain than its evidence.
