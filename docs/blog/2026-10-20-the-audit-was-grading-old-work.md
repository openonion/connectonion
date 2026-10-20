# The audit was grading old work

`co rem enrich` and `co rem muse` could each take one page deeper, but only when someone ran them by hand, one page at a time. Most of the notebook stayed exactly as it was on the night it was first written. On one real notebook, 93 of 141 pages quoted nobody at all. So the next step looked obvious: put both commands on the schedule. Each slot picks the pages that are worth the most and have the least on them, runs enrich and then muse, and gives the page one more round the next time it comes up.

Before trusting that loop with the whole notebook, we ran it on a copy: four people and two projects, two rounds each. The first round surprised us. The pages had gained quotes, from 3 to 15, but lost text, 46.4k characters down to 44.9k. One person page went from 9.8k characters to 7.3k and lost five of its source ids.

The cause was the claim audit. Every time a run finishes, an independent model checks the page's claims against their originals, and it was checking the whole page. Enrich and muse are additive passes, so most of what the audit read were lines the run had not written: a last-contact date, a sentence about the relationship, both written by init weeks earlier. In 11 of 12 runs the audit flagged one of those old lines. Each run then paid for two repair turns, and in the end the last resort deleted the flagged lines. A loop that runs on every slot would slowly erase the pages it was meant to deepen.

Now enrich and muse are judged only on the lines they wrote. A finding on a carried line goes into `claim-review.json` as `carried_findings`, where anyone can see it, but it no longer causes a refusal. In round two, 11 of 12 audits passed. Characters went from 44.9k to 46.1k, quotes from 15 to 30, sources from 121 to 133. There were 9 insights in each round.

Repairs also got cheaper. A repair turn used to start a fresh thread, and that thread re-read every original before it could fix a single sentence. Now it resumes the thread that wrote the page, which already holds those originals. 96 to 99 percent of a repair's input came from cache.

A round costs about 0.8 points of the Codex week. Deepening has its own 30-point budget, so roughly 35 page-rounds fit in a week. Round N starts from the open leads and questions round N-1 left, and in the trial a lead one round left open was followed by the next.

What is still shallow: projects. A project with two thousand reachable items got 600 characters deeper in two rounds. For a sub-project inside a monorepo, the pull requests that hold its history were gathered and then mostly ignored.
