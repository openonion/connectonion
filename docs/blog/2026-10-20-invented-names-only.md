# Invented names only

The reader's tests run against an invented notebook: Avery Lin, Mara
Ostrowski, Fernhill Labs. Two tests added this week broke that rule. A test
for merging duplicate waiting items and a test for Chinese history dates
used names copied from the bug reports that prompted them. The bug reports came
from a real notebook, and the names went into the repository with the fix.

They are now invented names, and every reader change runs a check before its
pull request is opened. The check takes the names of people and organisations
in the owner's own notebook, compares them with the lines the change adds,
and prints any match on the local machine only. A failing check stops the pull request.

The lesson is about where examples come from. A bug found on real data is
best reproduced with invented data before anyone writes the test. If the test is
written straight from the report, the report's names come with it.
