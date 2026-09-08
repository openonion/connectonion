# The suite was green and a thread was spinning

The test named in the timeout was a scroll test. Running it alone did not explain
why the complete Linux suite kept stopping there. The thread dump showed another
kind of work: registry cleanup threads created by earlier tests were still alive.
When a later test replaced sleep with a no-op, those old workers could keep
running through their loops.

That changed what a passing test needed to mean. A returned assertion was not
proof that the work it started had ended. The session registry now starts its
cleanup worker with the server lifespan and stops it on exit. The test fixture
also checks for threads left behind, so the failure belongs to the test that
created the worker rather than whichever test runs next.

The first CI run under that rule found another leak. `test_kill_task_and_missing`
had successfully asked a background task to terminate. Its output reader was
still running. The task used `shell=True`; terminating the shell could leave its
child holding the output pipe open. The reader had no end-of-file to read.

The repair follows that ownership boundary. A POSIX background task gets its own
process group. Termination targets that group, waits for the process and joins
the reader; a child that ignores termination can require a bounded forced stop.
Windows uses the task's process tree. The reader closes its pipe before it
finishes. The regression checks that termination has actually reaped the process
and retired the thread, rather than trusting the confirmation string.

The harder regression starts a child that ignores the first termination signal.
The shell can exit while that child still owns the pipe. The test now waits for
the reader to retire and checks the closed stream; a friendly "terminated"
message alone cannot satisfy it. That case passed locally with the bounded
forced stop.

The original scroll test had been the place unfinished work became visible.
The new failure belonged to the background-task test itself. That was the useful
change: cleanup became part of the operation being tested, with an owner and a
checkable end, instead of a promise left for the next test to discover.

The local run does not reproduce every Linux scheduling condition or prove that
all workers are gone. It gives the next leaked thread a shorter journey from
cause to failure. The thread guard remains enabled.
