---
description: co rem: a lock that kept letting the thread that just left cut back in, a test that only failed on slow CI, and three pages that waited ten minutes for a turn that never came.
tags: [REM, Reliability]
---

# The lock that let you cut in line

A first run of co rem writes pages with sixteen workers at once, and every
write to the notebook goes through one lock. In the 1.9.2b2 trial three
organisation pages waited ten minutes for that lock and then gave up. The
notebook had not been held for ten minutes. It had been free many times.
Each time, someone else got it first.

We had already fixed half of this. Waiting threads used to poll the lock and
sleep in between, so a waiter would wake up, find it taken, and sleep again
while busy threads passed it back and forth. So we put the threads of one
process in a queue before the file lock, a plain `threading.Lock`, and the
next run lost no pages.

Then a test started failing on CI. It had nothing to do with the change it was
blocking: a waiter has to get the lock while eight busy threads keep taking
it. It passed on our machines and on three Python versions, and failed on the
fourth, on a slow runner, with "co rem is busy". It went on to block three
unrelated merges and a release.

The queue was not a queue. CPython's lock makes no promise about who goes
next. A thread that has just released the lock is still running; it asks
again at once, and it usually wins against a thread that has to be woken
first. So the busy threads kept cutting back in, and the waiter waited until
its time ran out. A fast machine hid it, because the waiter's turn came up by
chance before the deadline.

The new lock hands out turns in the order threads asked. A waiter takes it
only when it is free and the waiter is first in line. A thread that just let
go joins the back. We wrote a test for exactly the case that had hidden: one
thread takes the lock twenty times back to back while another waits. On the
old lock the waiter got in after the third or fourth turn, in two runs of
three. On the new one it gets the next turn, thirty runs out of thirty.

"Queue the threads" was the right idea, and the class we picked for the queue
never promised to be one.
