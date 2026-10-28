# RC26 candidate acceptance

This preview repairs investigation-history noise and remaining local setup
omissions (issue #2696). The normal Codex 26.924.22138/profile remained in use;
no App replacement, different account or raw native database writes were used.

## Completed local trials

- Read-only CLI inventory found 1,428 eligible older internal conversations in
  the production notebook. Native read/archive RPC repaired them. The final
  read-only CLI inventory reports 0 eligible. A native active-list query then
  identified 3 legacy Desktop-origin REM delegates, which were independently
  recognized by their fixed prompt and private workspace and archived too.
  Actual terminal captures are in
  this release's assets. This is metadata/API acceptance, not a native UI capture.
- The first batch ended after 1,296 archived, 3 kept and an RPC error. Read-only
  reconciliation found the error's same scoped ID already archived, with its
  trace in the native archive. Completed outcomes were retained. After adding
  authoritative outcome reconciliation, retry archived 128 remaining candidates
  and the cohort reached 0 eligible. An unknown/unarchived RPC error still fails.
- The repair retains archive/resume data. Candidate selection requires this
  notebook's reserved task workspace, ConnectOnion originator or fixed legacy
  REM delegate prompt, no pin and age
  over one hour; workers refresh pin/age/cwd and native ID/runtime metadata.
  Native archive processes descendants, so a read-only recursive family check
  keeps a parent when any unarchived child is protected or unknown. Each
  unarchived family member receives a native runtime check, and family metadata
  and membership are checked again before the archive request.
  No model turn is used. Normal automation failure results remain outside scope.
- A separate one-off operation repaired proven internal traces in earlier
  managed trial notebooks without recreating deleted notebooks. The original
  read-only cohort contained 15,103 records; final metadata reconciliation found
  all 15,103 archived. The final guarded batch archived 724 with 0 failures. Remaining
  eligible records across managed trial roots: 0. Recent archived pinned records: 0.
  The final production native active-list query returned 0 and no next cursor.
- Actual CLI init fixtures use a synthetic home/project and offline backend.
  Installed rc22 retains the old link and incomplete profile. Candidate source
  refreshes that link and fills fields; both preserve the custom metadata.
  These images do not claim an empty Codex account or real customer service test.

## Independent AI review and regression evidence

A founder/marketing/UI AI role reviewer identified a stale pin/age guard and
partial-failure receipt/closure gaps before bulk repair. Revised guards passed
independent source-only reproductions. The focused suite reported 134 passed;
additional history guards reported 14 passed, then 15 passed including the live
archive-race regression. Final source/release matrices, installed-wheel checks,
actual rendered site views and postpublication acceptance are recorded in the
release PR/workflow. No human founder participation is claimed.

The final local broad run before the descendant refinement passed 17,611 tests
with 336 skipped. The installed-wheel trial passed 13 tests. Additional focused
regressions cover protected/unknown descendant metadata and runtime, plus
retaining all completed sibling outcomes when reconciliation cannot read the
database. Final-head CI is required before release.

## Limits

Other uncaptured native/remote UI states, live service/billing behavior, precise
requested-minute scheduling, account-managed native registration and complete
machine restart recovery are outside this repair's acceptance. Missing personal
skill source files stay personal; init does not invent or delete those files.
