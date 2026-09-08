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

Another CI failure was less dramatic. A long missing-skill path wrapped between
`missing` and `-skill`, so a useful diagnostic no longer contained the name the
test expected. The diagnostic now keeps the path intact. Shortening the test
path would only have hidden the next long path someone supplied.

The same suite audit added an offline network guard and removed competing test
configuration. A test that swallows a connection error can still be caught for
attempting that connection. Those guards are deliberately left enabled while
fixing their failures. They are how an earlier test's unfinished work becomes a
local, named problem instead of a mystery much later in the run.

These changes do not prove the absence of every resource leak or reproduce every
Linux scheduling condition on a Mac. They make two observable obligations harder
to evade: a test owns the worker it started, and an offline test must stay offline.
