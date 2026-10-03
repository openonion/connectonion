# Four copies of the same long help walk

A small reader fix waited more than eleven minutes for PR tests. Most jobs
finished in three; four Python-version jobs kept running. The suite was already
using both hosted CPU workers, so adding `-n auto` again would not help.

The slowest test was a useful one. It starts `co --help` as an agent would,
follows every listed subcommand, then runs the same pages as a person would in
a terminal. It catches commands an agent cannot find, examples that do not
match their pages, and help that changes when colour is enabled. On the measured
PR it took 276 seconds in Python 3.10 and 284 seconds in 3.12. Four copies of
that complete walk ran in parallel, once per supported interpreter. The other
offline tests still had thousands of assertions to finish behind it.

The walk now has a `slow` marker and one dedicated job on Python 3.12. Every
PR, main push, and release-tag verification calls the same workflow, so the
contract still runs before a release can publish. The four Python jobs continue
to run the rest of the offline suite, including shorter help tests. The change
removes three duplicate full walks and lets the ordinary suite and help walk
finish alongside each other.

This is a scheduling change, not a weaker contract. The next CI run must show
both the new help job and the four version jobs passing. Its measured critical
path and runner time will tell us whether this actually makes review faster.
