# Session-owned watches for COAI

Status: implemented for the 1.9.0 milestone, 2026-09-26. Related: [#1499](https://github.com/openonion/connectonion/issues/1499), [#339](https://github.com/openonion/connectonion/issues/339), [#353](https://github.com/openonion/connectonion/issues/353).

## Problem and boundary

COAI can start a long task and poll `task_output()`, but cannot leave a watch behind that brings the result back to the same conversation after the current AI turn ends. A user may also ask it to check something periodically, such as mail every 30 minutes, and report relevant changes without keeping an LLM call open.

A **watch** is created by the Agent during a session. It observes a specific task or runs a bounded read-only probe on an interval. Its output is an observation, not a user request or an AI answer. The Host delivers the observation into that same session and starts another AI turn so the Agent can inspect, decide, and explain. This feature does not use `co listen` as its product API: `co listen` admits messages from a configured external channel, while a watch belongs to a session and is created by that session's Agent.

```mermaid
sequenceDiagram
    participant User
    participant Agent as COAI session
    participant Host as Host watch runtime
    participant Source as Task or read-only probe

    User->>Agent: Start the long task and tell me when it finishes
    Agent->>Source: Start task
    Agent->>Host: Create watch for task completion
    Agent-->>User: Task started; I will check its result
    Note over Agent: This turn ends; no model call waits
    Source-->>Host: Finished, with exit status and bounded output
    Host->>Host: Persist observation for the original session
    Host->>Agent: Claim next turn with watch event
    Agent->>Source: Inspect result if needed
    Agent-->>User: Outcome and evidence
```

“Same session” means the same session ID, owner, history, and Workroom. It is a **new turn**, not a half-hour-long model call or a second Agent writing concurrently to the history.

## Product behavior

### One-time task completion

1. The Agent starts a managed background task and receives a durable task ID.
2. The Agent creates a one-time `task_completed` watch for that ID. Creating the watch is visible in the session. Registration checks an existing terminal receipt, so a task that finishes between steps 1 and 2 is not missed.
3. On completion or failure, the task runner records the exit status and bounded output, then the watch records one observation.
4. The Host starts a new turn in the original session. The Agent checks the result and reports it. An exit code is evidence; the monitor never asserts that the user's broader goal succeeded.
5. The watch becomes complete after its observation is delivered. Cancelling the task or watch has an explicit recorded outcome.

If the Host restarts and cannot prove the task's final exit status, the observation is `outcome_unknown` and says why. It must not infer success from a missing process. The task runner should write its own terminal receipt before exiting so normal restart recovery can distinguish completed, failed, and unknown tasks.

### Repeating checks

The Agent can create a watch such as “check this mailbox every 30 minutes for new mail about CRCD.” A watch has an interval, a named read-only probe, bounded arguments, a cursor, and a stop condition or expiry. The Host runs the probe without invoking the LLM on each tick. The probe returns `{changed, observation, next_cursor}`. No change updates the last-check time and cursor but does not wake the AI. A change persists an observation and wakes the original session once; multiple changes while a turn is busy can be grouped into one bounded batch.

The first repeating probe is new mail since a cursor. A generic extension point may let a custom Agent register other **explicitly watchable read-only probes**. Arbitrary shell commands and arbitrary tool names are not accepted as unattended repeating probes. A probe that needs interactive approval pauses the watch and reports that state instead of silently expanding permissions. The cursor and any resulting observation are committed together; a crash cannot advance the cursor while losing the message that should wake the AI. On restart, an overdue recurring watch checks once, rather than replaying every missed interval.

The Agent can list and cancel its watches. A probe error pauses the watch; the owner can cancel and recreate it after fixing the source. The owner sees what is being checked and the last/next check. V1 limits watch creation to the authenticated Host owner; a contact's ability to send a prompt does not grant them recurring access to the owner's mail or task results.

### Where it runs

The first implementation targets a long-lived `co ai` Host session (`co ai` server mode, local or deployed). The Host owns the watch scheduler and session store, so a browser or terminal client may disconnect while watches continue. `co ai "one-shot prompt"` exits after its answer; it must refuse creating a persistent watch with a clear explanation unless a long-lived Host is attached. It must never claim that an in-process daemon thread will outlive the CLI process. Automatic local Host startup for one-shot work can be considered later.

## Runtime model

Use one Host-owned watch store under the agent's `.co/` directory, with atomic claims for watches and pending observations. SQLite from the Python standard library is suitable here because a watch may fire as a user turn finishes, and two workers must not start two turns for the same session. Keep this feature's store separate from the global `schedule.yaml`: schedules are operator-authored jobs, while watches are Agent-authored and session-bound.

Minimum records:

| Record | Required fields |
| --- | --- |
| Watch | `watch_id`, `session_id`, verified owner, kind, task/probe reference, interval, cursor, next check, expiry, status |
| Observation | stable `event_id`, `watch_id`, observed time, source outcome, bounded payload, delivery state |
| Managed task receipt | task ID, process identity, start/end time, exit status, bounded output reference |

One dispatcher owns **one active Agent turn per session**. An observation arriving during a turn is persisted and delivered after that turn; it does not mutate the live message list from a background thread. User prompts and watch observations use the same session claim, so whichever is claimed first runs first. The next turn may receive a bounded batch of pending observations. The session owner and Host permission ceiling come from the durable session record, never from watch payload text.

The Agent sees a structured `watch_event` with source, watch ID, event ID, timestamp, and observation. Session Sync renders it as a `Watch observation` card using the existing tool-call ChatItem shape, tagged with `source: watch_event` for clients that want a distinct presentation. It is never a message authored by the user or the Agent's conclusion. The model receives a framed textual representation, but the event remains untrusted source data. The AI's reply is a separate assistant message. A wake-up starts in Read only mode and cannot inherit a temporary Full access grant or a previous approval.

Delivery is **at least once** across crashes. Persist the observation before claiming a turn; record its event ID in the session trace and settle it only after the resulting turn is durable. On restart, an unsettled event is retried. The dispatcher checks the trace for an already applied event ID to avoid duplicate visible messages. Failed or busy delivery waits at least 60 seconds before retry. No claim of exactly-once external side effects is made; an unattended wake-up cannot bypass approval for such effects.

An active watch keeps its session available until the watch ends or expires. V1 sets a bounded lifetime (default: 7 days), a minimum repeating interval (1 minute), and a per-session active-watch cap (10).

## Relationship to current code

- `cli/co_ai/tools/background.py` has a process-global task registry and `task_output()` polling. It needs a durable completion receipt and notification path for watched tasks; merely adding a callback to the daemon reader thread will fail across process exit or restart.
- `useful_plugins/runtime_input.py` drains client input into an **active** turn and seals the window at completion. Watch delivery needs a separate idle-session wake-up path; it should not impersonate `RUNTIME_INPUT` or a client `INPUT`.
- `network/host/schedule.py` already demonstrates a Host lifespan ticker and durable claim, but scheduled `run` creates its own turn/session. Reuse its lifecycle pattern, not its operator-authored schedule format.
- `network/host/http_router.py` and the session claim are the point at which a watch-triggered turn must preserve the original session, verified owner, mode ceiling, and history. A plain `input_handler(prompt="watch says...")` would mislabel the source as a user prompt.
- Workroom/Session Sync must expose the watch event and the later assistant turn on reconnect, including when no browser is connected at trigger time. Push notification outside the session is a separate feature.

## Implementation sequence

1. **Session wake-up contract:** define `watch_event` storage, owner binding, serialization with user turns, event-ID replay behavior, and Workroom rendering. Prove an injected test observation starts a new turn in the same completed session, including no connected browser and a busy-session race.
2. **Managed task completion:** persist a task receipt, let the Agent watch a task ID, and drive the session wake-up from real success, failure, cancellation, and restart-unknown outcomes. Preserve `task_output()` for manual inspection.
3. **Repeating probe:** add the Host tick, cursor-based Gmail search, no-change suppression, bounded observations, cancellation, and restart recovery. Prove “every 30 minutes” using a controllable clock rather than waiting in a test.
4. **User surface and installed acceptance:** expose watches and watch events in session data; verify a real long task and a real mail account in an installed Host/O Chat path. Provider-dependent live acceptance remains separate from offline tests.

## Acceptance examples

- A 30-minute task ends after the Agent's first turn. The original session receives exactly one visible completion observation and a new AI explanation. Reconnecting from another device shows both in order.
- A watched task fails with exit code 2. The AI receives that status and cannot display a success badge from the watch alone.
- A mail watch checks at 10:00 and 10:30 with no new mail: no AI turns. At 11:00, two new messages produce one observation and one AI turn. A restart at 10:45 does not reset the cursor or replay old mail.
- An observation arrives while the AI is answering a user. It waits; only one Agent turn writes the session at a time.
- A user cancels the watch; later source changes do not wake the Agent. A one-shot CLI attempt to create a persistent watch gives a truthful unsupported-runtime result.

## Decisions

The first runtime is a long-lived `co ai` Host. One-shot CLI cannot create persistent watches. A repeating check wakes the AI on new Gmail search matches, while an unchanged check only updates watch status. Wake-up turns start in Read only mode and cannot inherit Full access.
