# Every Rule Was Paid For

The deploy said success. The service said active. The balance page said
there was credit. And the agent had not answered a single question in three
days, because the key it was actually running with belonged to an account
that had run dry.

That is the incident behind one line in the new `deploy-agent` skill: *the
only deploy check that counts is to take the key the service really runs
with, ask the billing ledger who it is, and whether it spent anything today.*
Everything else on that page was a proxy. Proxies were green. The thing they
stood for was not.

The skill grew out of a few months of running an agent for people who were
not going to read logs. Each section is one incident, reduced to the rule
that would have prevented it. The stale-snapshot rule exists because a local
pipeline run left a cache directory that rsync happily shipped, and the agent
then answered from a copy of the world that was a week old. The "tell the
agent where the authoritative data is" rule exists because, without that
pointer, one question about a record count turned into a filesystem crawl
that cost $1.97 and 1.28 million tokens, and still came back with the stale
number. The row-identity rule exists because two files with the same name in
different folders became one row that flipped between two states every
night.

The first draft of this guide was a case study. It named the customer, their
systems, and their stack, because that is how the lessons were learned. It
was also under NDA, and the name had made it into a commit message, which is
why the first branch was abandoned rather than amended: a later commit
removing a name leaves it readable in history. This is the same material on
a fresh branch, with the identifying detail gone and the engineering kept. "Feishu Base" became one example beside Airtable, Notion,
and Sheets, because the incremental-write rules apply to any table a human
also edits by hand.

What surprised us on rereading was how little of the guide is about
ConnectOnion. State outside the rsync root, incremental diffs with normalized
values, provenance on every machine-filled number, a sandboxed dashboard
with data baked in server-side: these are the rules of putting any agent in
front of people who will trust its answers. The framework only decides where
the files go.
