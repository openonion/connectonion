# What the page already cites

The acceptance run investigated Richard, then investigated him again straight
away, to check that a page with nothing new costs nothing. The second run
spent 102 thousand tokens. The model read one email and reported, correctly,
that it was "already represented as source [21]".

The rule had been written a week earlier: a page investigated before reads
only the window since then, and an empty window makes no model call. It
worked for Tamara, whose window really was empty. For Richard it could not,
because the window is counted in whole days, and "since today" is today. The
email that had arrived that morning was still inside it.

We could have made the window finer. The page offered a simpler test, because
it already records what it has read: every fact it keeps is cited by the
source id of the message it came from. A gathered message whose id is already
in the page's Sources is not new to that page, whatever its date. So those are
dropped before the turn, the coverage says how many, and when nothing is left
the run ends without a model call and says why.

The same run left a question we could not answer. Earlier, a one-day
investigation took eight minutes, and its record held only a total time and
the last stage it reached. It did not say whether the time went on fetching
mail, starting Codex, the model's turn or validating the page. Each stage now
adds its own seconds to the run record, so the next slow run will show where
the time went.
