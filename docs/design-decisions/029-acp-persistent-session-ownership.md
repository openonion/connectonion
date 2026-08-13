# Design Decision: Persist ACP Sessions Under One Runtime-Long Lease

**Status:** Accepted
**Date:** 2026-08-10
**Related:** [011 Global Config and Identity](011-global-config-identity-management.md), [017 Session Logging and Eval Format](017-session-logging-and-eval-format.md), [019 Agent Lifecycle](019-agent-lifecycle-design.md), [021 Task Storage JSONL](021-task-storage-jsonl-design.md), [025 Interruptible Agent Steps](025-interruptible-agent-steps.md), [026 Structured Turn Outcomes](026-structured-turn-outcomes.md), [028 ACP Ordered Event Bridge](028-acp-ordered-event-bridge.md)

## Decision

Persistent ACP sessions use the same private, versioned JSON envelope as
machine-readable one-shot `co ai` sessions. A snapshot contains the complete
JSON-compatible Agent session plus only tool state with an explicit snapshot
contract. Its ID is a canonical UUID, its resolved working directory is part of
its ownership boundary, and a completed write uses a private temporary file,
`fsync`, and atomic replacement.

`session/new` acquires an OS-backed exclusive lease and writes the initial
empty snapshot before returning its ID. `session/resume` acquires that same
lease, then validates the ID, snapshot version and shape, and requested working
directory before constructing an Agent or granting it filesystem tools. The
lease remains held across every prompt until `session/close`, stdio EOF, or
failed runtime construction. Lock files are private regular files and symbolic
links are not followed where the operating system supports that guarantee.
Resume failures preserve the distinction required at the ACP boundary: an
invalid canonical ID is invalid parameters, an absent snapshot is resource not
found, a held lease is the shared session-conflict extension, and every other
integrity, workspace, quota, or storage failure is internal error. Wire error
data is fixed and bounded; raw exception text and Host paths never reach a
network peer.
The current tool contract accepts only TodoList items with string `content` and
`active_form` fields plus a known `status`; unknown tools or malformed items
fail before Agent construction.

Each prompt is a transaction over a detached last-good session and supported
tool-state checkpoint:

- `end_turn` and `max_turn_requests` atomically persist the complete new state
  after all ordered ACP updates have drained, then advance the checkpoint.
- cancellation, refusal, Agent/provider failure, client update failure,
  persistence failure, or async request cancellation before the commit phase
  leaves the disk snapshot untouched and restores both in-memory session and
  tool state.
- after a successful terminal turn enters its commit phase, that operation is
  cancellation-shielded. Atomic replacement is the commit point: success
  advances disk and memory together even if the waiting request is cancelled;
  failure restores the previous checkpoint. Ownership is retained until that
  outcome is fully settled.
- if rollback itself fails, the runtime is quarantined and releases its lease
  only after its worker has settled; a clean runtime can then resume the last
  disk checkpoint.

Close and EOF mark a runtime unavailable, interrupt active work, wait until the
worker can no longer mutate Agent state, and only then release ownership. This
supersedes DD-028's bounded failed-worker settlement for persistent ACP
runtimes. Releasing after a timeout would permit a new owner to resume while an
old worker was still changing the same logical session.

The adapter advertises ACP `session/resume` and `session/close`, keeps
`loadSession=false`, and never replays historical transcript updates. The
pinned ACP Python SDK gates these schema routes behind its
`use_unstable_protocol` transport flag, so the production stdio server enables
that compatibility flag while continuing to validate and return the official
models.

## Why

Locking only the load and save calls prevents simultaneous file replacement but
does not prevent two long-lived Agents from independently advancing the same
snapshot. The later writer would silently erase the earlier conversation and
tool state. Runtime-long ownership makes the single writer explicit.

Skipping a failed save is also insufficient in a long-lived process. The
failed turn has already mutated `current_session` and stateful tools, so a later
successful prompt would otherwise commit those abandoned mutations. A detached
checkpoint and rollback make the atomic disk boundary the actual conversation
boundary.

Resume is intentionally not transcript replay. An ACP client already owns what
it rendered; resuming restores the Agent's private continuation state without
duplicating old user, assistant, or tool updates on the wire.

## Consequences

Only one process or runtime can own a session ID at a time. Explicit close and
normal EOF make it immediately resumable elsewhere without deleting its
snapshot. A worker that ignores cooperative interruption can delay close: this
is preferable to releasing a lease while that worker can still mutate state.
Lease contention is reported as retryable session conflict rather than missing
state, so a client retains the valid session identity while waiting for release.
Because commit is non-cancellable once started, a client that disconnects at
that boundary must resume before deciding whether to retry its prompt.

ACP runtimes omit process-local background task tools because their handles
cannot survive a process boundary. Snapshot evolution requires a new explicit
version and validation path. Listing, loading/replaying, forking, deletion,
retention, and migrations remain separate features.

## Rejected alternatives

- **Lock each prompt only:** another runtime can load the same old snapshot
  between prompts and later overwrite valid work.
- **Release ownership after a shutdown timeout:** an abandoned worker can race
  the new owner and violate the single-writer invariant.
- **Keep only disk rollback:** the next prompt can persist mutations from the
  failed turn.
- **Pickle Agent and tool objects:** executable deserialization and
  process-local handles are not a safe persistence contract.
- **Replay history during resume:** duplicates client-visible events and
  confuses restore with ACP `session/load`.
- **Add a second ACP snapshot format:** creates divergent validation,
  migration, and security behavior for the same Agent session.
