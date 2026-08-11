# DD-042: Stable ACP plans are canonical session state, not review authority

**Status:** Accepted

**Date:** 2026-08-12

**Related:** [028 Ordered ACP Event Bridge](028-acp-ordered-event-bridge.md), [029 Persistent ACP Session Ownership](029-acp-persistent-session-ownership.md), [035 Versioned ACP Host Carrier](035-versioned-acp-host-carrier.md), [041 Public ACP Host Thoughts](041-public-acp-host-thoughts.md)

## Context

ConnectOnion already has two nearby concepts. `TodoList` tracks execution tasks
with content, status, and an active display form. `plan_review` pauses execution
so a human can approve or reject proposed markdown. ACP v1.19 `plan` is neither
a transcript message nor an approval: it is a complete replacement of the
current session's observable task list.

The active browser path is Host -> `@connectonion/react` -> O Chat. React owns
protocol decoding and exposes typed session state; O Chat renders that state.
The standalone TypeScript SDK is retired.

## Decision

`TodoList` is the canonical producer of session plan state. Every entry has
`content`, `status`, `active_form`, and an explicit ACP priority. Existing calls
remain compatible because priority defaults to `medium`; `high` and `low` are
opt-in. Successful state-changing `add`, `start`, `complete`, `remove`,
`update`, and `clear` operations publish exactly one complete replacement.
Rejected and no-op operations publish nothing. An empty replacement clears the
plan.

Agent tool injection supplies a hidden `agent` argument to TodoList methods.
Direct TodoList use without an Agent remains local. A revocable hosted call
mutates a private TodoList fork, not the shared instance. The method calls the
private `Agent._record_plan()` path only after its forked mutation succeeds.
Agent validates and detaches the complete list, stores it at
`current_session.plan`, and records a canonical `type=plan` trace transition.
The executor commits the fork and copied session together only after the tool
succeeds. Private methods stay excluded from tool discovery.

The Host maps only a persisted-trace plan event to the official ACP
`AgentPlanUpdate`. Persistence provenance remains the private WebSocket IO dict
subtype introduced by DD-041 and is preserved through an interruptible tool IO
lease. Persisted trace events and their `session_sync` are buffered by that
lease until the tool transaction commits; cancellation or failure discards the
buffer and fork, so provisional plans never reach a client or a later snapshot.
An ordinary `agent.io.send({"type": "plan", ...})` is still a legacy event and
cannot become an ACP plan. This is a cooperative same-process boundary, not a
hostile-plugin sandbox.

ACP v1.19 plan has no plan or message ID. The Host does not fabricate one.
Session ownership and complete-replacement semantics provide idempotency. The
Host sends the ACP notification immediately before the matching legacy
`type=plan` replacement. A mapper failure logs and skips only the additive ACP
frame; legacy delivery, session state, and terminal `OUTPUT` continue.

The one-shot/persistent `co ai` snapshot envelope advances from v1 to v2. V2
TodoList state requires priority. A v1 snapshot is validated with its exact old
shape, migrated in memory with `priority=medium`, and given canonical session
plan state before Agent construction. V1 allowed empty content; those entries
receive the deterministic label `Untitled legacy task N` because stable ACP
cannot represent empty content. Any pre-existing v1 plan field is rebuilt from
the migrated TodoList because v1 never owned that field. V2 requires the
session plan to equal the TodoList-derived plan exactly on save and load. New
high/low values round-trip through tool state and the session snapshot. Unknown
versions, malformed values, and divergent v2 state remain fail-closed.
Transaction rollback restores both session plan and tool state at the existing
atomic checkpoint.

`plan_review` remains unchanged. Observing progress never grants permission,
changes approval mode, resumes execution, or answers a review. Experimental ACP
`plan_update` and `plan_removed` are not emitted; they require a separate
versioned decision after stabilisation.

## Compatibility and rollback

Updated React readers replace their per-session plan state and de-duplicate the
legacy twin by value. Older clients keep receiving the legacy replacement.
Session sync, reconnect, final output, persistent resume, cross-worker storage,
and cancellation rollback all carry the same canonical current state.

Rollback stops mirroring `plan` and stops Agent publication. Stored v2 snapshots
still need a reader that understands priority; downgrading snapshot format is a
data migration, not a carrier toggle. The legacy browser event remains until a
separate major-version removal decision.

## Rejected alternatives

- **Map `plan_review`:** confuses progress visibility with execution authority.
- **Infer plans from tool calls/results or markdown:** creates a second source of
  truth and cannot represent reconnect state reliably.
- **Put plans in transcript ChatItems:** fabricates message identity and append
  semantics for replacement state.
- **Emit experimental incremental plan models:** binds the product to unstable
  protocol and requires IDs the stable model does not have.
- **Keep snapshot v1 and make priority optional forever:** hides a schema change
  and prevents strict validation or safe rollback planning.
- **Trust a JSON provenance flag:** direct IO callers could forge it.
