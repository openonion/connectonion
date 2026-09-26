# When a Wiki page claims too much

A Wiki investigation can produce a readable page and still leave the wrong
impression. In one test, the page's status line named a source that the run had
never searched. A reader would reasonably take that line as evidence of
coverage. The body could be careful, yet the footer made the whole page sound
more thoroughly researched than it was.

The same test exposed a different failure. The model retained the project's
original map values, but indented them under a nearby bullet. The validator
rejected the candidate, even though those values had not changed. Simply
relaxing validation would be dangerous: a changed session count or date should
still be caught. The repair therefore restores only values that exactly match
the original map, then runs the existing validator.

We also tried a shorter investigation instruction. It used less time in that
single comparison, but the candidate missed relevant implementation files.
That result did not earn a promotion. A faster page that overlooks primary
evidence is not a better memory.

The benchmark now separates execution, source coverage, factual support,
timing, and cost. It treats an existing citation as a pointer to inspect, not
proof that the sentence is true. The useful rule is simple: say what was
actually searched, preserve known facts without silently changing them, and
let evidence quality decide whether a faster method is worth using.
