# The Model Was Right, and the Benchmark Still Failed It

The first real run of `co eval run` scored a reimbursement skill on five
cases, and every case failed. Every expectation in every case had passed.
The mixed batch was handled correctly: the invoice addressed to the wrong
company was held back, the duplicate was submitted once, the one with no
amount was sent back to the user. The ledger the submit tool writes to
agreed with all of it. And the report said 0 of 5.

It said so because the skill never ran. The Agent had a `skill` tool and a
reimbursement skill it could load, and the model did the job without either.
That is what a benchmark for a skill has to catch, and it is the easiest thing
to miss: an evaluation that grades the answer will call this a pass, and the
developer will go on editing a file that does nothing. So a named skill is a
check of its own. With `--invoke auto` the trace has to show
`skill(name=...)` returning success; with `--invoke explicit` the skills plugin
has to have replaced `/reimbursement ...` with the skill's instructions, which
is the only trace that path leaves. A case where it did not happen fails,
however good the answer was.

Run two used explicit invocation and a deliberately naive skill — submit
everything, tell the user it has been paid. Three forbidden outcomes: the
wrong-company invoice submitted, the duplicate submitted twice, "paid" said
about something only pending approval. Run three changed nothing but
`SKILL.md`: five of five, and the report named the two cases that had
started passing. That is the whole loop #1642 asked for, and the benchmark
file did not change by a byte between the runs; its hash is in every report
to prove it.

Three decisions made that loop trustworthy rather than merely green.

The judge does not grade. It answers one narrower question per statement —
did this outcome occur, not occur, or can the run not show it — and code turns
that into a verdict. For a `must`, occurred is PASS. For a `must_not`,
occurred is a hard FAIL. A model asked "did the agent pass?" drifts toward
yes; a model asked "was INV-302 submitted?" looks at the tool call.

Claims are not effects. The judge sees what the tools actually did — name,
arguments, status, result — and an outcome that changes the world counts as
occurred only if a tool result shows it. An agent that writes "submitted, all
done" with no submit call gets UNVERIFIED, which fails the run like anything
else that is not a pass.

A run is evidence, so it is never edited. The older `co eval` wrote its
results back into the YAML a person authored; the standard and the score lived
in one file, and every run rewrote the standard. Here the benchmark is read
and never written, and each run is a new read-only directory. The first
version of that directory was named by the second and a random suffix, and a
test that saved twice in one second found the "run before" could be the run
after. It is named by the microsecond now.

The score had a quieter version of the first bug. It counted expectations,
so the run where the skill never ran scored 100%, and the next run looked
like a regression. The score is taken over checks now — every expectation,
plus "did the skill run" — and a comparison between runs with a different
invoke mode or model says that it is comparing different setups.

Writing the tests turned up one more thing, not in the benchmark at all.
`Agent(tools=[skill])` — the documented way to let an Agent choose a skill —
could not be constructed: the tool annotates its injected agent as
`'Agent'`, imported only for type checking, and resolving the annotation
raised `NameError`. Nobody had built that Agent, so nobody had noticed. The
benchmark's own tests were the first to try.
