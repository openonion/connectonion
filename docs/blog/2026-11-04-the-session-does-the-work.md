# The session does the work now

The night REM moved onto Codex's own scheduler, the trace of each run looked
like this: a Codex session starts, runs one command, and waits. For an hour.
The command was `co rem sync --scheduled`, and inside it REM was starting its
own Codex processes, one per model step, the way it always had. The outer
session did nothing but hold the line open, and it paid for that: between
100k and 360k tokens per run, by the audit in #2747, for a session whose only
output was "the command finished".

The owner's question was the obvious one. If the scheduled task is already a
Codex session, why does it call a program that starts more Codex sessions? It
should be the executor.

The answer had to do with how REM was built. Every stage, extraction,
maintenance, investigation, enrichment, translation, was one function that
prepared a prompt, called the model, and checked the result, with the call in
the middle and the check depending on local variables from the preparation.
Nothing in that shape could hand the middle step to someone else.

The first attempt at fixing this did hand it over, by snapshotting the whole
notebook before each step and replaying the stage afterwards against the
snapshot. It worked, and it was rejected: 438 MB copied per operation on a real
notebook, a crash between the page write and the checkpoint left the notebook
half-committed, and a resubmit the next morning was refused because the prompt
said yesterday's date. A transaction engine had grown where a function split
was needed.

The split is what shipped. Each stage now has `prepare()`, which collects the
evidence and writes the prompt and the candidate file, and `check()`, which
validates and promotes. The child-runner path calls the same codex turn between
them and behaves as before. A native session instead runs `co rem next`, which
does the non-model work once per round, advances a cursor kept in one small
JSON file, writes one task directory, prints the instructions and the submit
command, and exits. The session writes the file and runs `co rem submit`,
which checks that the inputs it hashed at prepare time are unchanged, runs the
same validators sync runs, promotes the page, and advances the cursor. The
date in the prompt is the date it was prepared; a receipt written beside the
page lets a death between the write and the cursor advance be reconciled
without another model turn.

The round itself had to become resumable too. An investigation runs several
bounded turns on one page, each carrying leads from the last, and those leads
had lived in Python locals. They are in the cursor now, and a unit test
continues three investigation parts across three separate Python processes.

The acceptance run on a copied notebook: one Codex session, six tasks in six
minutes, every submission accepted, no child process. The person page it
maintained gained five cited sources, lost an `Unknown`, and recorded an
identity match as an open question instead of a claim. That last one is the
kind of edit the validators exist to protect, and the native path produced it
with the same checks.

What is still owed: the native round is a second implementation of the daily
round, 394 lines beside `daily.py`, and the two must move together until the
child path retires. It is written down in the PR, which is where debt belongs.
