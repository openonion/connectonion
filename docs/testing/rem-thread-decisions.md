# Done and Skip persistence — 2026-11-07

Done and Skip are stored in `.state/threads.json`, keyed by the reader's existing
page-path + original-thread-text done key. Each decision records `state`, `at`
and `device`, and a `draft_id` when a current draft exists. Mail `versions`
preserve the message observed when skipping, including offline replay. A batch
also retains its linked `keys`, so one Undo restores the entire action.

`POST /rem/thread` accepts `{key, state}` (`done`, `skipped`, or `open` for Undo).
The reader optionally supplies observed versions, device and merged/batch keys.
`GET /rem/thread` reconciles the latest decisions. Both use the same loopback,
Host-header and owner-cookie checks as `/rem/draft`; POST requires JSON. Shared
snapshots omit the private decision keys. The live reader renders its snapshot
before reconciliation, and retries pending browser actions on load, focus and
reconnection. Cached successful decisions are not replayed as new actions.

Skip retains the prepared body and suppresses the same mail version in daily
and native draft queues. New mail returns the item with the message date. Native
submission also rechecks decisions made while drafting. The five-second toast
and the record's Undo restore the decision; a collapsed decision history keeps
Undo available if the original Markdown bullet was rewritten or removed.

## Independent review and fixes

An independent AI reviewer adopted a technology founder, marketing and UI role.
This is a role-based review, not participation by a human founder.

| Priority | Problem and impact | Evidence | Improvement and recheck |
| --- | --- | --- | --- |
| P1 | Copied/approximately merged obligations could reappear or be drafted again | Temporary notebook reproduction; browser/Python grouping differs | Persist all reader member keys in one batch; copied-obligation regression checks queue and census |
| P1 | Skip/reload/Undo lost the visible body | Owner listing removed skipped body | Keep skipped body in owner snapshot; regression restores prepared body |
| P1 | Offline Skip could suppress mail received before reconnection | Server captured replay-time version | Send observed versions; regression verifies dated return and preserves an already prepared newer reply |
| P1 | One Skip spanning multiple obligations left some skipped after toast Undo | Separate per-item toast handlers | One batch request and Undo; regression restores every key and body |
| P2 | Reconciliation could delay the first render | Load awaited network | Render inline state first, reconcile afterward |
| P2 | Rewritten thread bullet removed permanent Undo | Record enumerated only current bullets | Durable collapsed record history; removed-bullet regression |
| P2 | Offline Undo could temporarily leave linked aliases hidden | Cached successful responses dropped linked keys | Retain cached keys and undo them together; offline-batch regression |
| P2 | Offline wording implied notebook persistence | Completed details used unconditional saved copy | Pending-sync copy in fallback states; mobile screenshot |

## Verification

Red-first run: eight expected failures for the missing state module, endpoint,
reconciliation and undo. Final requested selection: **830 passed**. Existing
DeprecationWarnings remain unrelated to this change.

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit -k "reader or proactive or next_submit or daily or live_reader" -n 6
```

Rendered checks use a fictional one-thread notebook and a dedicated `co browser`
tab. Desktop home and post-Skip empty state, mobile record Skip/Done, offline
pending-sync, dated new-mail return, and rewritten-thread history states were inspected. Waiting count becomes zero after Skip;
record Undo is visible with a 44px height and no horizontal overflow. Browser
DOM verification confirmed notebook persistence, immediate Undo, disappearance
of the toast after 5.15 seconds, and retained record Undo. Pending state is saved
in localStorage while the notebook remains unchanged until reconnection. Reload
replayed the pending action successfully. The dated new-mail return and Undo
from history after removing the original bullet were also verified in the
browser; that history Undo cleared the server decision.

Screenshots are local under `/tmp/frontend-test-screenshots/rem-thread-actions/`.
The independent reviewer inspected desktop home/post-Skip and mobile record
Skip/Done/offline/returned-mail/history screenshots. No significant issue
remained in the final independent review. Automated new-context browser acceptance is in
`tests/e2e/cli/test_rem_thread_actions_browser.py`; Chrome launch aborted in this
sandbox, so two independent browser contexts were not exercised. The existing
browser daemon supplied the manual rendered checks. Coverage is these states,
not an all-page or physical-device pass.
