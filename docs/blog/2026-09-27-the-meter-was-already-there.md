# The meter was already there

The owner asked a simple question about the wiki's first pass: can it spend
10% of the tokens, and how much is that? I answered with an estimate. I took
the tokens per item from seven nightly runs, guessed the cost of an
investigation from them, and got about 7 million input tokens. It was a
careful estimate. It was also the wrong kind of answer, because the owner
had said 额度, the quota on their Codex plan, and I had turned it into tokens
since tokens were all we measured.

Our own docs had given up on the real answer. "Not implemented: hard 2%
initialization / 1% daily subscription spending limits. They need an actual
provider meter." That sentence had sat there for weeks, and everyone
reading it believed there was no meter.

There was. Every Codex session file on the owner's machine carried it:
`rate_limits.primary.used_percent: 5`, a 10,080-minute window, a reset time
and the plan. And `codex app-server`, which our Codex tool already drives,
answers `account/rateLimits/read` without starting a turn, so reading it
costs nothing. We had been driving the process that knew the answer, and
only ever asked it to write code.

So the wiki now reads the meter before and after every run and records the
difference, and "10%" means ten points of the owner's week. The
investigation round adds up its own points since the week reset and stops at
its budget. It also stops, whatever budget is left, once the week passes 70%,
because the wiki shares that quota with the owner's real work. The status
line says it plainly: 5% used on Pro, resets Sunday, investigation 0 of 10
points.

We wrote the doc and the tests before the code, as the owner asked, and it
paid off before any code existed. Writing "every figure is good to one
point" into the doc forced us to notice that Codex reports whole percents.
That is why the budget sums each run's movement instead of comparing the
week's first and last readings: the owner's own coding moves the same meter
in between.

The lesson: before you estimate a number, check whether the system you are
already talking to can tell you what it is.
