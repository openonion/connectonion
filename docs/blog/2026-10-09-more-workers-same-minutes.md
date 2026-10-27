---
description: co rem 1.9.2b2: tripling the workers did not shorten the first run, and what did change once we looked at every page.
tags: [REM, Performance]
---

# More workers, same minutes

The first run took 138 minutes, and we wanted 45. A replay of 338 real runs
said 48 workers and three rounds a page would get there. So we tried it on the
same mailbox.

It took 130 minutes. In the first 66 minutes, 48 workers finished 161 runs; 16
had finished 167. Each model turn simply took three times as long. The queue was
never the limit. The provider's throughput was, and the replay had assumed a
turn costs the same however many run at once.

The extra workers did find something, though. Fourteen pages failed waiting for
a lock: forty-eight threads were each retaking it between one saved message and
the next, while a waiter slept a second between tries. Threads now queue. The
next run lost none.

The cap of three rounds did what the workers could not. It cut the cost by a
sixth.

Then we read every page of a real notebook, 289 of them, screenshots and text,
on a desktop and on a phone. Most were useful; 221 needed a fix. The worst were
small and specific: someone else's phone number, copied from a signature quoted
in the thread. Our first fix kept only numbers from a person's own signature. It
also took off a number someone had given in plain words, "give me a call on…".
So the rule is narrower now: a number is removed only when the mail shows whose
it is, and it is someone else's.

A wrong number is worse than none. Throwing away the right ones to avoid it is
not much better.

## 23 October: what the tests were waiting for

Candidate test change; not a new REM runtime release.

The same question came back about CI: would more workers make it faster? The
three Python jobs were already concurrent, and each used two pytest workers.
Their coverage job still took eleven to thirteen minutes. That observation did
not tell us whether more processes on the same runner would help.

The slow-test report gave us a smaller answer first. A simulated mailbox stayed
down for every retry. The test correctly kept the other mailbox's result, but
before proving it, waited one, two, four and eight real seconds. Two other tests
preserved earlier years after an interrupted import and waited two, four and
eight seconds each. No mailbox was being contacted. The failures were invented;
the waiting was real.

We kept the retries and recorded the requested delays instead. The tests now
check every delay and the final failed attempt, including that there is no extra
sleep afterward. Their existing retained-data and healthy-source checks remain.
The identical three-test command went from 45.76 seconds to 0.68 seconds. A first
added assertion confused Graph's shortened query with Gmail's domain query; we
corrected the assertion rather than changing the working search behavior.

That is a useful saving, but not forty-three seconds off parallel CI. Other work
may occupy the second worker, and the whole coverage job still needs measurement.
The production backoff, coverage floor, timeout and release gates are unchanged.
The lesson from the longer first-run experiment still holds: find what time is
being spent on before multiplying workers. Here, the unnecessary resource was
elapsed time inside synthetic tests. Runner sharding and real REM page quality
remain separate questions.
