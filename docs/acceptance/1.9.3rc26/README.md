# RC26 candidate acceptance

This preview repairs investigation-history noise and remaining local setup
omissions (issue2696). The normal Codex26.924.22138/profile remained in use;
no App replacement, different account or raw native database writes were used.

## Completed local trials

- Read-only CLI inventory found1,428 eligible older internal conversations in
  the production notebook. Native read/archive RPC repaired them. The final
  read-only CLI inventory reports0eligible; actual terminal captures are in
  this release's assets. This is metadata/API acceptance, not a native UI capture.
- The first batch ended after1,296archived,3kept and an RPC error. Read-only
  reconciliation found the error's same scoped ID already archived, with its
  trace in the native archive. Completed outcomes were retained. After adding
  authoritative outcome reconciliation, retry archived128remaining candidates
  and the cohort reached0eligible. An unknown/unarchived RPC error still fails.
- The repair retains archive/resume data. Candidate selection requires this
  notebook's reserved task workspace, ConnectOnion originator, no pin and age
  over one hour; workers refresh pin/age/cwd and native ID/runtime metadata.
  No model turn is used. Normal automation failure results remain outside scope.
- A separate one-off operation is processing the same proven internal traces
  in earlier managed trial notebooks; that broader result is recorded in the
  release PR after completion, separately from the current-notebook acceptance.
- Actual CLI init fixtures use a synthetic home/project and offline backend.
  Installed rc22 retains the old link and incomplete profile. Candidate source
  refreshes that link and fills fields; both preserve the custom metadata.
  These images do not claim an empty Codex account or real customer service test.

## Independent AI review and regression evidence

A founder/marketing/UI AI role reviewer identified a stale pin/age guard and
partial-failure receipt/closure gaps before bulk repair. Revised guards passed
independent source-only reproductions. The focused suite reported134passed;
additional history guards reported14passed, then15passed including the live
archive-race regression. Final source/release matrices, installed-wheel checks,
actual rendered site views and postpublication acceptance are recorded in the
release PR/workflow. No human founder participation is claimed.

## Limits

Other uncaptured native/remote UI states, live service/billing behavior, precise
requested-minute scheduling, account-managed native registration and complete
machine restart recovery are outside this repair's acceptance. Missing personal
skill source files stay personal; init does not invent or delete those files.
