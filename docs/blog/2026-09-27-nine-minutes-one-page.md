# Nine minutes, one page

At 08:42 on 27 September the owner's notebook ran its update by hand, the way
the schedule would run it that night. It failed. The log said "Record not
found: projects/projects-09300d1d65.md", and a list of 118 changed pages sat
above the error.

The update had not broken anything. The owner had run `co wiki init` a few
minutes earlier, and the map was still rebuilding when the update started. The
map archived that project page while the update was writing to it. Because
pages had changed, the failed batch counted as progress, and 40 messages would
have been marked read without ever reaching a page. Every test passed, because
no test ran the two at the same time.

The fix is one lock. The map now takes the same lock the update takes, so
whichever starts second is told the Wiki is busy and writes nothing. The test
for it holds the lock, runs the map, and checks that no map file appears. It
failed on the old code.

At 08:54 we ran the update again on the same 40 messages. It finished in nine
minutes. It worked on the three pages the material was about and changed one,
the project the sessions had run in. That morning the same batch had spent
twenty minutes and saved nothing.

Three other changes shipped in the same preview. The Wiki can now read the
weekly meter Codex shows the owner, so `co wiki investigate all --budget 10`
means ten points of this week and stops there. A page the map just made opens
on what is known instead of ten lines of "Unknown". And a hosted agent that
resumes a session keeps its instructions: before this fix, an agent told its
name was Zephyr answered "Gemini".

What the budget can buy is still small. Investigating the owner's own page
read 16 million tokens, so ten points reaches only a few pages. Before `init`
can start a first pass on its own, investigation has to get cheaper.
