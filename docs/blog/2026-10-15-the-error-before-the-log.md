---
title: "The error before the log"
date: 2026-10-15
---

REM's old nightly failure had an odd shape. The system scheduler had an error to show, but the notebook's own run list stopped several days earlier. The page could describe the next scheduled slot without describing the read that had failed.

The rewritten-session case now has a handler: keep the old checkpoint, record the skipped file, and continue with healthy sessions. That repair is already in the published package. Repeating it would miss the remaining boundary.

A synthetic source with invalid metadata exposed that boundary in the current preview. Collection happened before the run record was created. The reader raised a controlled error, so execution never reached the code responsible for explaining a failed pass. No model had run, but a real operation had failed.

The follow-up gives that failure a record. It names the source and gathering stage, records zero model calls, and leaves source progress unchanged. The existing scheduler can then record the outcome and stop retrying the same owed slot every five minutes. The terminal names the failed source instead of showing only a total of zero changed pages.

That choice has a cost: a temporary source failure waits until the next scheduled slot unless the owner retries manually. We chose a visible, bounded failure over an automatic loop with no durable account of what happened. Unknown programming errors still propagate; they are not dressed up as ordinary source failures.

Seventeen isolated regressions pass, including plain and JSON command results. None reads a real mailbox or runs a model. Real scheduled acceptance and safe recovery of skipped transcripts remain open. A useful error record is necessary for trusting the night; it does not prove the night remembered anything useful.

Independent review additionally found uncaught provider exceptions and a daily-wrapper message that called a gathering failure an investigation failure. Both are corrected, including safe mailbox configuration recovery and a scheduled daily-wrapper regression.
