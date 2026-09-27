# The busiest project was the folder

The owner's notebook had 938 pages after init, and 725 of them were
outlines. The fix looked obvious: give the first pass a budget, 10 points of
the Codex week, and let it work down the queue from the busiest page. We wrote
the doc, then the tests, then the code: `co wiki investigate all --budget 10`,
one queue over people, projects and organisations, with a check of the week
before every page.

Every test passed. Then we asked the real notebook for its order, with
`--list`, which runs no model. Second and third were Ody Zhou, 185 mails, and
the ConnectOnion project, 92 sessions, which is exactly who and what the owner
works with. First, with 813 sessions, was a project called "projects".

It was the owner's `~/projects` folder, the workspace that holds every repo.
Every coding session run from there had been counted as work on one project,
so the folder outweighed everything real by a factor of four. A budgeted first
pass would have spent most of its ten points reading 813 sessions about
nothing in particular, then reported success.

The tests could not have caught this. They used a queue we built by hand, and
a hand-built queue has no workspace folder in it. It took the real data, read
without spending anything, to show that the busiest item was not the most
important one.

So the feature shipped as built, and the first pass waits. The folder went to
#1844, the map-noise issue, as the thing that must land before anyone runs a
budgeted first pass on a real notebook.

The lesson: before you let a budget run down a ranked list, read the top of
that list from real data, for free.
