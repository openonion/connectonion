# The first run that cost a dollar

A tester installed 1.8.8b9 into an empty home directory and did what a new
user does. `co create my-agent`. `co benchmark list`, which printed an example
benchmark about invoice reimbursement. A one-line skill. Then the command the
help pointed at: `co eval run reimbursement --agent agent.py --skill
reimbursement --invoke explicit --runs 1`.

It ran for five minutes and fifty seconds and spent about a dollar of the five
free dollars a new account starts with. The report scored one case out of five.

The skill was fine. The example was not. Its first case said "Please process
these three invoices", and there were no invoices, not in the input, not in the
project, nowhere. The agent that `co create` makes is a capable coding agent,
and a capable coding agent that is asked about invoices it cannot see goes
looking. It globbed the workspace, grepped it, and read its own `.co/logs`,
up to 26 steps a case. Every step was a paid model call. The judge then marked
most answers UNVERIFIED, correctly, because "submitted for approval" is an
outside effect and no tool had done any submitting. The standard we printed
could not be met by any agent, and running it was expensive.

The next line in the help made it worse. It suggested `--runs 3`. That is
three dollars of five, spent learning that the example cannot pass.

We had tested this command many times, always with suites we had written
ourselves, where each case carried its own data. What we had never done is run
the example exactly as we printed it, as the first thing a new user runs. A
default is part of the product. So is an example, and a hint, and the order in
which the help lists things.

So the example changed. Every case now carries its data in the input. The
invoice numbers, the buyer on each one, whether a receipt is attached, the
date an earlier submission went in. Every expectation is something the reply
itself shows: "the reply flags INV-202 because its buyer is not OpenOnion Pty
Ltd", not "INV-202 is not submitted". A correct agent can answer each case in a
step or two without searching, and it needs no tool that changes anything to
pass honestly.

The runner changed too, because the next person's first benchmark will have the
same gap in some other form. `co eval run` now lowers the agent's own loop
limit to 10 steps for the run. An attempt that reaches the limit is STOPPED,
which counts as a failure. It is not judged, so no judge call is spent on a
"Task incomplete" answer, and `--max-iterations N` raises the limit for a task
that really needs more steps. Before the first model call, the run says how
many agent runs it is about to make and how far each may go. With `--runs` above
1 and no saved run yet, it suggests starting with one. The report ends with what
the agent's model calls actually cost.

The same afternoon produced a list of smaller things that are also only
visible from an empty home directory, and the pattern is the same in each. `co
create` into an existing folder said "exists" in red and exited 0, and so did
`co deploy` with no agent.py, so a script carried on as though both had worked.
`co init ./` in an empty folder finished by suggesting `co deploy`, which could
only fail. `co doctor` printed "nothing wrong" directly under its own warning
that another `co` came first on PATH, and gave a green tick to a `co` that
crashed when asked its version. `connect(addr).input()` from a machine with no
identity reported "signed request required" and did not say where a signature
comes from. The host terminal printed the trust engine's internal reasoning at
every stranger, and labelled a client of the same version "legacy". The banner
said 10 skills while `/info` said none. Both were right, and neither said what
it was counting. The wheel still shipped our planning notes and fifty design
records into every new project's `.co/docs`. And the onboarding page called
invite codes one-time, when one code had just admitted two people.

None of these is hard to fix. Each was invisible to us for the same reason. We
use the product from a machine that is already set up, so we never saw what it
does for someone whose machine is not.
