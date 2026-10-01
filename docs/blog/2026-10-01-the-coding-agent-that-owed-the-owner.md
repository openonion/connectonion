# The coding agent that owed the owner a status

The 1.9.0a6 acceptance run ended on the page that matters most, the owner's
own. Under Open threads it said "Claude Code owes the user a message-volume
check" and "Codex owes the user a status". Its Last contact was a Claude Code
session. Nothing on it was false, exactly. The owner had asked Claude Code for
that check, and Codex had not finished. But no colleague owed him anything
there. He had been talking to his own tools, and the page had written them up
as people.

The rule for the page was not missing. It said "what they are working on now,
from the coding sessions". The turn had 1,477 session messages to read and
cited three, so it never got to his projects at all. What it did read, it read
the way a person's page reads mail: someone asks, someone owes an answer. We
added the rule it needed, that a coding agent is the owner's tool and never a
counterparty, a correspondent or a last contact. We also stopped asking the
model to find the projects in the sessions, because the map already knows
them. The owner's turn now gets the projects of the four weeks before the
map's own date, with their session counts and dates, newest first. The lead
has to name the busiest of them.

The same notebook had three smaller pages that looked fine until we checked
where their claims came from. Tidy had folded two of the owner's addresses
into his page, and they sat after the one address that had a citation, with
none of their own. Further down, Uncertainties still said it was unresolved
whether those two were his. Each folded address now cites the map entry that
made it his, and an Uncertainties line about addresses that are all his now
is removed and logged.

The daily round had spent 100,080 tokens on "Flagship Minerals"
\<ceo@flagshipminerals.com\>, a mining company's investor update, as if it
were a person. Nothing in the address says no-reply. The giveaway was the
display name, which is the domain written out as words. A person on that
domain writes under their own name. The map now treats a sender whose name
spells its domain as a service. The people queue applies the same rule to rows
an older map left behind. On the copy of the notebook that excluded twelve
pages: Apple, Pinterest, DEV Community and the like, plus Flagship.

The last one was an archive that never finished. At init, co rem saves a
private copy of 90 days of mail so that later investigations can read it
locally. On this notebook it had stopped at 550 of 3,152 bodies the day
before, and its state file still said `running`. Every investigation since had
skipped it and gone to the mail servers, and status had nothing to say about
it. The state file now records when it last made progress. After ten quiet
minutes, `co rem status` and `co rem doctor` both report it, with the command
that resumes it. The next sync resumes it for up to five minutes at a time,
reusing every body already on disk.

All four come down to the same lesson. A page can look complete and still be
wrong about where its facts came from: tools listed as people, addresses with
no source, a company treated as someone to know, an archive that claimed to be
running. Each fix is a check that runs before the model gets the page.
