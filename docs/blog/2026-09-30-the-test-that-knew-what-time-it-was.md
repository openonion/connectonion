# The test that knew what time it was

1.9.0a2 was tagged at a commit whose tests had all passed, twice, in pull
request CI. Its release run failed. One test, on Python 3.11 and 3.13, wanted a
one-day update window and got two.

The test was about something real: a person investigated this morning who
writes again this afternoon should be updated from today's mail only. So it
marked the person investigated "three hours ago" and checked the window was one
day. Three hours ago is today, most of the day. The release run started at
00:08 UTC. Three hours before that was yesterday, and a window that starts
yesterday is two days long. The code was right. The test had quietly assumed it
would never run in the first three hours of a UTC day.

It passed in pull request CI because those runs happened in the afternoon, and
it would have passed again if we had re-run the release three hours later. We
did not want a release that depends on when you press the button, so the test
now sets its own clock, noon on a fixed day, and passes the same `now` to the
code it checks. The code already took a `now`; the test had not used it.

Since a pushed tag should not be moved, the fixed code ships as 1.9.0a3, with
1.9.0a2's content unchanged, and the notes say plainly that a2 was tagged and
never published.

The lesson: a test that reads the real clock is testing two things, the code
and the time of day. Give it a clock, or it will pick its moment to fail.
