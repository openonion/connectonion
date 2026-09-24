# The Wiki worked, but the small input was not cheap

On September 8, the question was whether the Wiki could keep a useful record
when someone changed their mind. Producing a page once would not answer it.
The next conversation had to change what the notebook said, and an assistant
had to be able to use that notebook afterward.

The test gave an isolated Codex session a small, synthetic project: Aurora
would store its notes as Markdown for portability. The Wiki made a project
page and a decision page. Then a later session corrected the reason. The
choice was still Markdown, but what mattered was inspectability, not
portability. SQLite was an alternative that had not been adopted.

That distinction was the point of the test. Keeping both reasons as current
would preserve the conversations while losing the decision. Creating another
decision page would leave the next reader to reconcile them. The Wiki instead
changed the existing decision. SQLite stayed a rejected alternative. A
separate Codex used the Wiki to answer a question, and another sync with
nothing new made no model call. The complete CLI journey, including start
and stop, passed in 77.89 seconds.

The pages gave a reassuring answer. The run journal complicated it.

The two maintenance batches took 25.4 and 21.4 seconds. Together they recorded
177,772 input tokens and 6,139 output tokens. Of that input, 151,040 tokens
were cached; they are included in the total, not added to it. These counts
covered maintenance only, not the separate Codex calls used to tell the
assistant something and ask it a question.

The task looked small from the conversation: one storage choice, then a
correction to its reason. The maintenance workload was not correspondingly
small. Those numbers did not establish which part of the run should be
optimized, nor did they establish a monetary price. They did show why counting
new messages alone would be a poor way to describe this run's cost. Reporting
only the finished pages or the elapsed seconds would have hidden that fact.

The unchanged sync offered one useful boundary: when there was nothing new,
the system did no inference. But that result could not explain away the work
spent on the two updates that mattered. The notebook had successfully revised
its understanding; making that revision's workload predictable remained a
separate problem.

This was one synthetic journey on one Mac, not a forecast for a person's
mailbox or months of conversations. At the time, both PRs remained drafts.
The other checks and their limits, including the browser, scheduler and
hostile-source tests, are recorded in the
[acceptance notes](../testing/wiki-acceptance.md#fresh-revalidation-2026-09-08).
They do not turn this example into a general safety or cost guarantee.

The useful result was a corrected decision that the next assistant could
retrieve. The unfinished part was visible only beside it, in the run journal:
what it had taken to produce that correction. A background notebook needs
both records before we can judge whether it is working well.
