# The meter that read 29% all week

co rem gives investigation a weekly budget: 10 points, where a point is one
percent of the owner's Codex week. Before each page it reads Codex's own meter,
and after the page it reads it again. The difference is what the page cost.
We liked that design because nothing in it was estimated. The meter belongs to
Codex, so a number from it is measured, not guessed.

Then the 1.9.0a7 acceptance run spent about 3.4 million input tokens on
investigations over a day, one page at a time. Every run record said the same
thing: 29% before, 29% after. At the end, `co rem status` said "0 of 10
investigation points this week". Going by the budget, a day of the most
expensive work the notebook does had cost nothing.

The meter was not wrong. Codex reports whole percents, and most of those
tokens were cached context that the agent re-sent every turn, which Codex
charges at a fraction. One page really did cost less than one percent of the
week. So every page measured zero, the zeros added up to zero, and a budget
meant to stop investigation at 10 points could never stop anything. The
`--budget 10` on a category run had the same blind spot, because it also read
the meter alone.

The fix keeps the measurement wherever there is one. If a run moves the
meter, that move is what the run cost. If it doesn't, the run counts its fresh
tokens instead: input minus cached input, plus output, at a million tokens a
point. That rate comes from the evidence, since it keeps the acceptance day
under one point, which is what the meter said. Status shows a decimal now
("0.7 of 10"), and the line under it says what a point is and when tokens
stand in for the meter.

The lesson: a measurement with coarse resolution is still a measurement, but
summing it in small pieces can lose everything. Below its resolution it
reports zero, and zeros never add up to anything. If you add up many small
readings, check that each one is big enough to register. If it isn't, find
another way to count it.
