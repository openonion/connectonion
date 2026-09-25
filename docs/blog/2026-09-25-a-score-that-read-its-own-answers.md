# A score that read its own answers

The last walk through 1.8.8b11 ran the benchmark flow exactly as the docs
describe it: `co create`, save the example benchmark, write a one-line skill,
`co eval run --runs 1`. It scored five out of five for thirteen cents. The
tester then opened the traces, which is the part nobody does when the score
is perfect.

In four of the five cases the agent's first move was `glob("**/*")`, and its
second was `read_file(".co/benchmarks/reimbursement.yaml")` — the file that
lists, for every case, what must and must not happen. A coding agent asked a
question it cannot answer from the prompt looks around the project, and the
answer key was in the project. The perfect score measured how well the agent
could read.

Nothing about this is exotic, which is why it matters. The benchmark feature
exists so that people stop trusting a skill because it looked right on the
example in front of them. A number that can be produced by reading the
expectations is worse than no number: it is confident.

So a run now closes the book before it starts. For as long as `co eval run`
drives the agent, any tool call that names the benchmark's file or earlier
eval runs is refused with a reason, and a case's declared fixture stays
readable. The refusal is a guard, not proof, so the runner also checks each
attempt's tool results for the expectation text: an attempt that saw the
answers anyway is INVALID — not judged, never a pass, and the run exits 1.
One trace had read the file by its absolute path, which is why hiding it from
the working directory would not have been enough.
