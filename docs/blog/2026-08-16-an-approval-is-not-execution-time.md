# An approval is not execution time

*2026-08-16*

A Work Room test asked Codex to create and test a small Dijkstra program. The
first action was deliberately harmless: inspect the workspace. The operator
read the approval, allowed it, and expected the coding run to continue.

Instead, the native app-server reported a turn timeout just under ten minutes
after the invocation began. The problem was not that Codex had spent ten
minutes computing. Our timer had spent the operator's review time as though it
were provider execution time.

That distinction matters most in a Work Room. The point of a manual approval
is to let a person stop and understand an action. Treating that pause as a
penalty turns careful review into a hidden failure mode: the next safe command
can inherit almost no time to run.

## Two clocks, one authority boundary

The Codex adapter still has a bounded active-execution budget. A genuinely hung
app-server can still time out, and an interrupt can still stop its process
tree. The change only separates the period spent waiting in the nested approval
callback from that active budget.

The adapter measures each approval callback and extends the turn wait by the
measured duration. It does not grant an action automatically, widen the
sandbox, or add a new protocol path. An approval remains an operator decision;
it just no longer erases the time needed to act on that decision.

For hosted co ai Codex runs, the default active budget is now thirty minutes.
That is still finite, but it reflects the scale of a coding agent that may
inspect a repository, edit files, run checks, and return a result rather than a
single shell command.

## Measure the pause without making the test slow

The regression test does not wait for a human. It advances a deterministic
clock through one hundred seconds of simulated approval review, then proves
that the following execution slice still has the full configured budget. A
second test verifies that the approval callback records exactly its measured
duration. Existing cancellation and hosted-routing tests cover the boundary
around it.

The lesson is small but reusable: a timeout is a statement about what work is
allowed to consume. Human review is not the same work as provider execution.
When a product asks someone to approve an action, the system must make room for
them to do that thoughtfully.
