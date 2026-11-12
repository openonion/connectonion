# Seventy-one minutes for nothing

A clean notebook had no connected mailbox and no imported coding sessions.
`co rem init --estimate-only` still offered two pages, about 13.8 million
billed input tokens, and 71 minutes. The map had found zero people and zero
projects. An installed skill was enough to make an empty first run look busy.

Two assumptions met in that number. The estimate-only path bypassed the
check that explains why the owner's page cannot be written without a mailbox
address. The planner then charged the average cost of a large notebook's
owner page twice, once for the quick pass and once for the full pass.

The fix starts with the material. No mailbox address means no owner page in
the plan, with the same explanation in preview and normal runs. Owner cost
scales with mapped mail items and usable sessions; zero material costs zero.
The scaling assumes 2,000 items reach the full owner rate and caps it there.
That threshold is a planning assumption, not a measured per-message price.
The existing notebook medians still supply the rate. We chose this bounded
estimate over another flat average; item counts cannot predict every retry
or the length of each source.

When no people or projects were mapped, installed skills do not start a
page queue by themselves. Init explains how to connect a mailbox or create
project history, then exits without the estimate question. Import summaries
also name their skip reasons: `3 skipped (program prompt)` tells someone
why three local files did not become three sessions.

There was a second stumble after a useful run. A fictional project called
Harbour could have a page at `projects/harbour-<hash>.md`, yet `co rem show
harbour` said no person matched. Bare names now search people, projects,
orgs and skills, including project folder names. Exact paths win. Ambiguous
names list the matching paths and display no page.

Regression tests reproduce the empty-map forecast, missing skip reasons
and failed project lookup before the implementation changes. The tests
use synthetic notebooks and mocked model boundaries; they do not establish
the accuracy of the new cost forecast on a live mailbox.
