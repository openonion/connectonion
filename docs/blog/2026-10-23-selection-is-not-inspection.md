# Selection is not inspection

A night band said “Read N items” and listed the run's sources. In sync, however,
the item count is filled before a model starts, while that source list contains
selected subscriptions. A failed mailbox could therefore appear beneath the
same reading count as a healthy local session. An older run without a count was
also turned into zero. Neither presentation explained the actual evidence.

The remaining attachment problem in issue #2045 has the same root: a file saved
and gathered into candidate input was labelled read, even when the model's own
report said it had not inspected the attachment. That report is not independent
proof either. The collector's observable action is gathering, before later input
selection and model work.

We considered inferring inspection from a successful outcome, dropping the counts,
and showing the available counts with their actual provenance. The candidate
chooses the last: recorded inputs, not inspected items; selection, not successful
source coverage; recorded failures, not a health certificate. A compact disclosure
compares those states without adding a new telemetry store. Missing and invalid
historic data stays unknown. Counts that disagree are not assigned to a convenient
source, and repeated per-run input is not called a unique memory.

Daily parent records need special care: they initialize zero counters without
retaining child input totals. Those defaults cannot establish zero input. The
reader marks that unmeasured aggregate unknown. New collection summaries say
bodies/attachments gathered; the queue still understands old read labels, so a
wording repair does not buy the same investigation again.

Seventeen initial reader contracts failed before the projection and labels were
added. Four collection/queue contracts failed before gathering labels and their
compatibility parser were repaired; one legacy parser control passed. Subsequent
controls cover missing selection, explicit empty selection, overflow and literal
source labels. These are source and logical Node contracts, not current native
screenshots or proof that a model examined every item.

This remains a candidate stacked on the partial-source repair. Public/installed
baseline is 1.9.3rc16. No real notebook was rewritten and no provider, model or
scheduled run was started. Native desktop/phone and accessibility, actual model
usefulness and complete historical source coverage remain unverified.

Independent review found the homepage headline still using the old “read” count.
The headline now uses the same validated recorded-input label, including unknown
counts, as the night summary and Activity. First-build and returning copy are
checked in both interface languages; this is not native visual acceptance.
