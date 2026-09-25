# The agent read the answer key

The last tester on 1.8.8b11 did what we tell every new user to do. They made
a project with `co create`, wrote a five-case reimbursement benchmark, and ran
`co eval run reimbursement --agent agent.py --runs 1`. It scored 5 out of 5,
and nobody was pleased, because the tester had opened the traces.

In four of the five cases the agent had not reasoned about invoices at all.
Its first step was `glob("**/*")`, to see what was in the workspace. Its second
was `read_file(".co/benchmarks/reimbursement.yaml")`. That file contains every
case, every `must` and every `must_not`. The agent under test found the marking
scheme sitting in the folder it was working in, read it, and wrote the answers
the marking scheme asked for. The judge saw correct answers and passed them.
The score was accurate and meant nothing.

We had built the benchmark on the idea that the standard is written before the
skill and never moves. We had not asked who else could read it. The `co create`
agent is a coding agent: listing the workspace is the first thing it does with
any task, and a YAML file named after the task is exactly what a careful coding
agent should open. It was doing its job. The benchmark was not.

The first fix we thought of was to hide the file, running each attempt in a
directory that does not contain `.co/benchmarks`. It fails on the same trace.
The first case read the file by its absolute path, which the agent knows from
its own prompt, and changing the directory does not change that path. So the
fix has two layers, and each covers what the other misses.

The first layer is a guard that runs before every tool call during
`co eval run`. It refuses any call whose arguments name `.co/benchmarks`,
`eval-runs` or the benchmark's own file name, and it tells the agent why. A
file a case declares as its `fixture:` is still readable, since it is there to
be read. When the run ends the guard is removed. We tested it with a real
Agent whose model does what the template did: it calls `read_file` on the
benchmark and then answers. The read fails, the attempt is scored on what the
agent does next, and the file's contents never reach it.

A path guard cannot see every way in. `grep -r INV-202 .` names no protected
path and still prints the benchmark's lines, and so does a shell pipeline or a
sub-agent the guard never hears from. The second layer does not depend on how
the agent got there. The run knows every expectation it is about to judge, so
after each attempt it looks for them in the tool results. An attempt whose
tools returned an expectation word for word is marked INVALID. It is not
judged, which also saves the judge call, it is never a pass, and the run
exits 1. The report says which tool returned which expectation.

The same tester kept finding the same shape of gap that afternoon, smaller
each time: a promise the docs made and the code did not quite keep. With no
browser running, `co browser tab ls` started one. A paid browser wrote its
profile under the real home even with `CO_BROWSER_PROFILE_DIR` set, and
`co wiki stop` under a test HOME stopped the real user's job. Each was an
isolation someone had relied on and nobody had checked from the outside.

The lesson is older than this bug. A measurement is only as honest as what the
thing being measured can reach. We had checked the judge's reasoning, the
exit codes and the cost of a run. We had never checked what the agent could
open while it was being tested.
