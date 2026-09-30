# The tests that read the room

Getting 1.9.0a4 out meant finding three tests that passed or failed depending
on where and when they ran, rather than on the code. One had already cost us a
release.

The first read the clock. It marked someone investigated "three hours ago" and
expected a one-day window. At 00:08 UTC, three hours ago was yesterday, and the
release run for 1.9.0a2 failed; nothing reached PyPI. The second pair read the
working directory. They checked that a relative PYTHONPATH came out absolute
by comparing it with "." resolved, and in a parallel run another test had
already moved the process somewhere else. The third started a second Python
process to hold a lock. That child imported connectonion from wherever the
path pointed, and after someone else's chdir it found an old installed copy
with no co rem at all, died, and the test said the lock was never held.

Each one passed on its own and in pull request CI, which is why they got
through. Each failed on the machine and at the moment where it mattered least
to the test and most to us: a release run, or a full local run before tagging.

The fixes are all the same move. The clock test sets its own noon. The path
tests pick their own directory and check the property, every entry absolute,
instead of one exact string. The lock test hands its child the checkout it
means to import.

The lesson: a test that reads the clock, the current directory or whatever is
installed is testing the room it runs in. Give it the room, or it will fail
in someone else's.
