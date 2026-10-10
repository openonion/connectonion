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
