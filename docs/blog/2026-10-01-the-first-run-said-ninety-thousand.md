# The first run said ninety thousand

On the morning of 1 October the owner ran `co rem init --days 14` on his own
mail and sessions, into a scratch notebook, the way a new user would. The map
took two minutes and was right: 656 mails, 82 people, 9 projects. Then the
first run started spending, and it had told him what to expect. Each project
page would cost "~90k billed input tokens" and take "about a minute".

The first project page took 614k tokens. The second took 922k. Each took four
to five minutes. A person page he stopped by hand when its own cost line said
it could reach 1.93M. Thirteen projects had been active in the fortnight, and
all thirteen were queued; the only thing that would have stopped them was the
Codex weekly meter. Left alone, the "first minutes" of a new notebook were on
course for well over ten million billed tokens.

The ninety thousand was not invented. It was measured, once, on 30 September:
a 47,000-character prompt that billed 86,710 input tokens. What that
measurement could not see was that the runner is an agent. It reads, runs a
command, reads again, and re-sends its whole context on every round. A small
test project took one round. A real project with five months of messages took
a dozen. The number was true for the page it was measured on and wrong for
every page a person actually has.

The obvious fix was a bigger constant. We nearly wrote "~750k per project"
into the code and moved on. But the next constant would be wrong the same way,
for the next notebook with longer threads or a faster model. The notebook
already keeps a record of every page it writes, with the tokens the runner
reported and the seconds it took. So the first run now asks its own notebook:
the median of the completed pages of each kind, and only before there are any,
the defaults measured that morning (680k for your page, 425k a person, 750k a
project). It adds them up and says one line before anything is spent: "About 7
pages (your page, 3 people and 3 projects), ~4.2M billed input tokens on your
own Codex plan, ~35 minutes (an estimate from runs measured on a real
notebook)." It is still an estimate, and the line says whose runs it came
from.

And it is capped. Three people, three projects, unless `--first-people` or
`--first-projects` asks for more. The people read the run's own `--days`, not
the 150 days a full investigation reads, which was the other reason the person
page ran away.

The same morning showed what the money bought. Your own page had written "Role:
Partner at OpenOnion, running marketing; Airbnb co-host" and cited a mail in
which the owner described Ody, his partner. A list of someone else's roles,
written by you, had become yours. The page also followed the person template to
the letter, down to "How the user writes to them: Not applicable", and turned a
month of coding sessions into a count. It now has its own short spec: who you
are and what you are working on now, from the sessions, dated; a role only when
you state it or someone states it about you; what you owe and are owed. The
project pages came back after 600k–900k tokens with five and six sections still
saying "Unknown — not investigated yet". A page that says it was not
investigated, right after it was, is now refused. The section says what the
material shows, or a bare "Unknown".

The lesson we keep relearning with co rem is the one about measurements taken
on the fixture. A number is only as good as the page it was measured on. When
the product already records what every real page cost, the honest estimate
comes from those records, and the constant is only the fallback for a notebook
that has none yet.
