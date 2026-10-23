# Recorded input coverage — candidate, 23 October 2026

Issue #2045; follows source-isolation draft2623. Public/installed baseline rc16;
source base fdccf68449d6479724d9fe1cf41fba151672a6ba. That base's24checks and
docs293's4checks passed, but native acceptance remains pending. This candidate
does not change those reviewed heads or claim the stack has shipped.

## Data-flow evidence

Sync writes items=len(items) before reserving a model call and sources from the
selected subscription keys. items_by_source is its independent input breakdown.
The reader instead labelled the count read and reused selected source names.
Daily parent _reserve initializes items=0/sources=[] without rolling up child
input counts. Generic numeric coercion also made missing data look like zero.
Investigation gathering labels counted body/attachment collection as read before
later input selection/model execution. The existing2045comment identifies this
same remaining supplied-versus-inspected ambiguity. No fresh real-data trial.

## Chosen correction

Use existing run records only. Show recorded input counts with unknown portions,
not unique memories or inspection counts. A compact semantic table compares
source selection, consistent recorded input counts and recorded failures. Failed
and unattempted sources are not called healthy or caught up. Missing/invalid
selection differs from an explicit empty list. Daily parent placeholders remain
unknown without a consistent measured breakdown. Repeated runs count repeatedly.

Accept only nonnegative safe-integer counters. Per-source totals must agree with
the run total before attribution. Missing, malformed, contradictory or overflowing
metadata remains unknown; literal source labels use text nodes, not HTML. Existing
local-material/feedback labels get readable names. No new archive or state store.

Fresh gathering text says bodies/attachments gathered, not read or inspected;
legacy read labels remain accepted by the queue's existing material heuristic.
The page filter recognizes new body-gathering metadata under its existing policy.
There is no automatic rewrite of saved pages, receipts or historical records.

## Verification and limits

Seventeen initial reader contracts failed before adding the projection/consumer
labels. Four actual synthetic collection/queue contracts failed before repairing
fresh labels and new-label queue compatibility; one legacy control passed.
Controls cover failed selection versus recorded input, later model failure,
zero/missing/invalid/mismatched counters, missing selection, repeated input,
overflow, parent defaults, bilingual copy and literal source-name text.
Final focused/full/independent/exact-head CI results are recorded in the PR.

The table has column and row headers, a native disclosure and a named focusable
horizontal-scroll region. These are semantic-source properties, not actual phone,
keyboard/focus or screen-reader acceptance. No native REM preview/HTTP/CDP/browser/
renderer/screenshot workaround, fresh init/provider/model/scheduler execution or
real notebook mutation. Model inspection and mature-product usefulness remain
unmeasured; issue2045 and native/release gates remain open.

Independent review caught a missed primary consumer: the homepage header still
said read N from pass.items. Twelve composed first/returning, partial/missing/
daily-parent and EN/ZH header cases failed before routing that header through the
same coverage projection. Its existing details link and focus action are retained.
The pre-header candidate passed 17,127 tests (334 skipped); that historical run
is not evidence for the amended head. Native acceptance remains pending.
