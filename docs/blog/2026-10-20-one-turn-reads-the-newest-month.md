# One turn reads the newest month

The ConnectOnion repository has a history going back to August 2025. We ran four rounds of enrich and muse on its project page. After all four, its Key decisions held three lines, and all three were from October 2026.

The whole history was right there: enrich already hands a project page a timeline, oldest first, month by month. But one model turn given fourteen months of pull requests behaves like a reader skimming a long thread. It reads the end and replies to that. Asking it to "walk from the first month" did not change where it spent its attention. There was a second cause too. The repository listing stopped at the newest 400 issues and 400 pull requests, so for the project's own repository, the timeline itself began in October.

Now a long history is cut into periods, each about 15k characters of timeline, six at most. Enrich reads them one at a time in the same resumed thread. Each turn studies one period, adds that period's turning points, and stops. A final turn follows the remaining leads as before. Because the thread is resumed, a later turn's input is mostly cached, so the extra turns cost little. The repository listing now pages through everything, up to 5,000 items. Listing 1,346 pull requests with their comments took 36 seconds.

The rounds also left History and Key decisions messy. The same decision showed up twice on one date in slightly different words, and a blank line split one list into two. Dates were already sorted in code. Now a same-date line contained in a longer one is merged into it, with its citations moved onto the longer line. A line carrying a quote the longer one lacks stays, because a quote glued onto another sentence reads as nonsense.

One rule changed from the last post. When a lost line is put back, it no longer replaces a writer's rewrite that cites something new. The rewrite stays, and the original goes in beside it.
