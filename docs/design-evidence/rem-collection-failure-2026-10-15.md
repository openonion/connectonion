# A failed source read must leave a failed pass (#2301)

## Current evidence

Latest observed preview: 1.9.3b1. This follow-up uses its SHA-256-verified public source distribution. Before editing, `service.py` matched main's published GitHub content. Rewritten-prefix isolation and scheduled warning reporting already exist and are preserved.

A different failure boundary remains: a controlled error while gathering a source can escape `_sync_locked` before its run record exists. The synthetic reproduction raised `RemError("Invalid session metadata")` from the collector; the command escaped without a durable failed pass. A scheduled call would therefore leave its slot owed and retry on the next tick.

## Change and tradeoff

Known collection errors (`RemError`, filesystem/encoding errors and explicit Outlook/Gmail transport/authentication exceptions) now produce a finished failed run with the source, gathering stage, zero model calls and unchanged progress. The existing scheduler records that failed outcome and serves the slot once; its existing status warning points to logs. Manual sync remains available for an explicit retry.

The terminal summary shows the failed source and reason. Arbitrary filesystem/encoding exception text is replaced by a safe diagnostic rather than copied into the result. Programmer errors continue to propagate. A failed gather does not immediately resume the mailbox archive, which could hide this failure behind a second source request or exception.

A recorded failure serves that scheduled slot; this intentionally favors bounded retries and a visible failure over repeated automatic attempts every five minutes. It does not implement reindexing or prove that skipped transcripts have been recovered. Issue #2301 must remain open for those acceptance requirements and a real scheduled trial.

## Verification

Seventeen isolated regressions cover controlled source/filesystem/encoding failures, preserved progress, zero model calls, durable records, same-slot retry suppression, attention status, mail collection, programmer-error propagation and plain/JSON CLI failure reporting. The first regression failed against the unmodified package. All seventeen pass with the fix.

```sh
python -m pytest tests/unit/test_rem_collection_failure.py -q
```

No real sources, mailboxes or model services were read. No live scheduler was installed or run. No rendered browser page or screenshot was produced: the UI change is a terminal failure summary, checked through the CLI. The owner will perform real-data acceptance manually. CI is required before merge or release. These regressions do not establish REM product maturity.

Independent review additionally found uncaught provider exceptions and a daily-wrapper message that called a gathering failure an investigation failure. Both are corrected, including safe mailbox configuration recovery and a scheduled daily-wrapper regression.

The separate AI reviewer rechecked the provider exception boundary, sanitized recovery, preserved daily-wrapper diagnosis, archive/investigation suppression and required dependency imports. No remaining blocker was found. This was read-only code/terminal-state review; no real human or browser review is claimed.
