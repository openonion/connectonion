# Attributed feedback processing — candidate evidence

Related to #2334 and the feedback loop in the product audit. This is a bounded
repair within shipped sync/daily maintenance, not the external-agent scheduler
migration or a claim that #2334 is complete. Candidate base: main
`000e4b96481ddb8e700dc4567ca7ea7f11e7a20e`. Not included in rc8.
Before PR, rebased onto rc8's reviewed merge
`c194f36b0f52c90ab3e3e1f63003ea47b545d29c`; only release metadata changed underneath
the already-tested implementation. Focused feedback/release checks rerun on that base.

## Source findings

- New local feedback could be marked consumed by an older cooldown/current-page
  early return; structured review subjects were absent from the context packet.
- A refused review or unattempted target beyond five pages/daily allowance could
  inherit the batch's consumed ID. Partial-write failure made that risk durable.
- Compact summary IDs represented views, so a changed view could replay old events.
- Independent review found cross-target input, lossy extraction, revision-insensitive
  filtering/refusal gating, uncapped feedback retries, and daily acceptance without
  a receipt. All are covered by the candidate's source/tests.

## Contract and tradeoffs

Raw event revision + target receipt; acknowledge accepted update/no-change only.
Explicit target routing bypasses ordinary cooldown/project-writer/current-source
skips for feedback, preserving those rules for ordinary source maintenance.
Per-target raw input is bounded conservatively using raw page length plus wrapper
allowance; this is not an exact serialized prompt-length guarantee. Oversized work
remains pending and does not suppress capture processing. No lossy extraction of
attributed feedback. Existing consent, locks, source rotation/cursors and retry cap
remain in force. Receipts express processing, never factual truth.

Native accepted promotion recovery requires saved page hash + retained event
revision. Prepared-before-write mismatch remains pending. Matching recovery persists
the receipt before deleting the proof. Custom callbacks cannot supply this native
crash proof. Legacy raw consumed IDs remain compatible; exact retained summaries
expand to known members. Overwritten summary membership explicitly defers affected
unreceipted reflections, including new records on that subject, for inspection.
There is no automatic legacy reconciliation command in this patch.

## Verification

Red-first evidence: original contract 6 failed/1 passed; revision/retry boundaries
2 failed/11 passed; extraction/revision refusal 4 failed/11 passed; daily acceptance
failed before the shared receipt; overwritten summary and native recovery 3 failed
before repair. Follow-up focused/related suites: **358 passed in 9.71s**.
The already-correct refusal/capture/no-change cases remain invariants, not claimed
newly discovered failures. Tests isolate HOME and network; no real model or provider.
Full offline suite: **16,093 passed, 160 skipped, 7 warnings in 125.21s** with
four workers, `TERM=xterm-256color`, and the CI-only dummy `OPENONION_API_KEY=test-key`.
Existing platform/browser/provider opt-ins remain skipped; no marker waiver.

Commands:

```bash
python -m pytest tests/unit/test_rem_feedback_receipts.py \
 tests/unit/test_rem_memory_preview.py tests/unit/test_rem_service.py \
 tests/unit/test_rem_page_review.py tests/unit/test_rem_runner.py \
 tests/unit/test_rem_daily_round.py tests/unit/test_rem_refusal_ledger.py -q
python -m pytest tests/ -n 4 --dist loadfile \
 -m 'not slow and not real_api and not network' -q
```

Independent AI source/test review approved PR preparation after the initial
blockers were repaired. No human founder review, fresh real init, real mailbox
collection, scheduler execution or active process restart. Existing local preview
security restriction remains; no screenshot workaround or current visual acceptance.
Reader markup/styles/layout unchanged. Raw run outcomes and future page contents
can change; that is data behavior, not proof of improved aesthetics or usefulness.
