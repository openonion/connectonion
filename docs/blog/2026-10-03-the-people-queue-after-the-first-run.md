# The people queue after the first run

The first REM run could investigate several pages together. After it ended, the
owner had another command for the people it left behind. That command showed
the cost and the order, then worked through people one at a time. On the
owner's notebook, one earlier 150-day person investigation took 15 minutes. A
queue of hundreds turned a useful resume command into a long wait.

The next batch now uses the same bounded worker path as the first run. It can
investigate up to four different people together, with separate mailbox
clients, and checks the weekly budget before starting each page. If the Codex
week is close to the safety floor, the batch starts fewer workers. Finished
results still appear in the order the owner was shown, even when the work
finishes out of order. A refused page remains in the queue without stopping
the other pages already underway.

A synthetic two-person run proved the investigations overlapped. Other tests
checked a refusal, a stopped budget, and the boundary where 89% of the Codex
week becomes 90% after one page. The broader REM regression passed 2,039
tests. These checks establish the dispatch behavior, not live mailbox
throughput or the quality of every resulting memory.

The private 730-day map currently has 324 people queued for full
investigation. We have not started that batch: the owner's Codex week was
already at 93%, past the notebook's 90% safety floor. The next trial needs to
measure actual time, tokens, completed and refused pages, and the evidence on
sampled desktop and phone pages. The budget stops new work; pages already
running can finish, so a 20-point run is an advisory limit rather than an
exact spending cap. The remaining historical coverage work is tracked in
[#2176](https://github.com/openonion/connectonion/issues/2176).
