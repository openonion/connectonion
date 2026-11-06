# Native REM follow-up review

Role-based AI review from a technology founder with marketing and UI experience.
All exercised notebook material was fictional. No real notebook was inspected.

## Findings and rechecks

| Priority | Problem and user impact | Evidence | Improvement and recheck |
| --- | --- | --- | --- |
| P1 | Audit instructions embedded a whole packet on one line, preventing inspection. | Original handler-matrix regression failed on cdb4a100. | Instructions point to separate readable packets. Check every prepared file across native handlers for lines over 4,000 characters. |
| P1 | A new scheduled turn could encounter an advisory live claim and stop. | Live-claim follow-up regression failed on cdb4a100. | Scheduled follow-ups reclaim pending work without allocating a second task. Recheck both live and dead claims after 15 minutes. |
| P1 | Finished rounds checked runner quota before returning not due. | Idle-follow-up regression failed on cdb4a100. | Check saved-slot eligibility first. Recheck with source collection, quota reads and reservations forbidden. |
| P1 | Blanket wrapping risked altering exact quotations and source text. | Independent implementation review. | Wrap generated reading views; preserve exact strings losslessly in JSON. Check long quoted pages and repository snapshots. |
| P1 | A null last-scheduled-slot value broke first-fire eligibility. | Independent implementation review. | Treat null as no previous slot. Recheck a first scheduled task with null worker state. |
| P1 | Normalizing arbitrary outputs could break repair of malformed JSON. | Independent reviewer reproduced an oversized malformed candidate. | Normalize generated material and state only. Recheck malformed output, refusal rendering, correction and resubmission. |
| P2 | Progress text claimed new mail was being read even on idle follow-ups. | Rendered CLI review. | Describe resuming work or checking whether a round is due. Recheck the idle output. |

## Inspected states and limits

Inspected actual rendered CLI output for a fictional writer task, claim audit,
acceptance and round completion, including task headers, workspace pointers,
submission commands and audit material sections. The header hierarchy and next
actions were clear. Checked exact recurrence/wake expansion, saved-time consent,
claim takeover, pending/next-task resumption and idle completion in tests.

Handler coverage includes extraction, maintenance/investigation writers, claim
audits, repairs, same-person comparison, translation, session summaries,
inquiry planning/synthesis, project writing/quote passes and skill evidence.
Project preparation includes a long fictional repository snapshot.

No browser page or mobile layout changed or was inspected. Local checks do not
verify actual Codex timer delivery or launchd wake delivery on a real notebook.
