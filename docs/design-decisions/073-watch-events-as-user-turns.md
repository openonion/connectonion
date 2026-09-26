# DD-073 — Watch events enter a Host session as user turns

Status: 1.8.9 preview proposal, under review in #1499 and #1781. Research checked 2026-09-26.

## What a watcher is

A watcher is a running observer plus a registration (what source and filter to
observe), an event delivery path, and optionally a durable cursor or queue. A
SQLite database is storage for the latter; a database by itself does not
observe files, receive webhooks, or wake an idle agent. The event must be
submitted through the ordinary session input boundary. Writing a row directly
into a transcript would bypass session claims, turn lifecycle, and failure
handling.

## Evidence from existing systems

| System | Observation | Delivery and persistence | Lesson |
| --- | --- | --- | --- |
| [Codex file watcher](https://github.com/openai/codex/blob/main/codex-rs/file-watcher/src/lib.rs) | `notify` registers OS file watches; subscribers receive coalesced paths through an in-process channel. | The watcher is separate from Codex's [queued user input](https://github.com/openai/codex/blob/main/codex-rs/ext/queue/src/service.rs). | Observing a change is not the same as submitting a user turn. |
| [Codex user queue](https://github.com/openai/codex/blob/main/codex-rs/ext/queue/src/service.rs) | Enqueue can come from another process; the service checks SQLite's data version periodically and tracks changed thread revisions. | A per-thread queue in SQLite waits for an idle thread, then calls `start_turn_if_idle`; an idle lifecycle callback also dispatches. | Durable queue, idle check, and normal turn submission are three distinct responsibilities. |
| [Claude Code hooks](https://code.claude.com/docs/en/hooks) | `FileChanged` matches literal watched paths and runs a hook on change. | Its `systemMessage` is a notification, not a user message. Ordinary async hook output waits for the next turn; `asyncRewake` can wake an idle session on a specific exit code. | Lifecycle hooks alone do not solve general external event delivery. |
| [Claude Code routines](https://code.claude.com/docs/en/routines) | Schedule, authenticated API call, or GitHub event triggers a run. | Each run creates a new session. API event text is wrapped as untrusted data. | Trigger-to-session is an established pattern, but session-per-event differs from this issue's continuing-session goal. |
| [Watchman subscriptions](https://facebook.github.io/watchman/docs/cmd/subscribe) | A daemon publishes file changes to connected subscribers; a saved clock can resume observation. | The subscriber still decides what to do with changes. A fresh instance or [recrawl](https://facebook.github.io/watchman/docs/troubleshooting) requires reconciliation. | OS notifications are hints; recovery needs a state check or a durable source cursor. |
| ConnectOnion Host | Existing inbox listeners and schedule ticks already run outside the agent loop. | Both call `input_handler()` and persist turns in `.co/session_results.jsonl`. Inbox uses a durable directory queue; schedule has its own JSON state. | Reuse the Host input boundary and process lifetime. |

The publicly inspectable Codex source confirms SQLite for queued user input
and thread state. It does not imply that its file watcher is implemented in
SQLite. Claude Code's public hook and routine documentation likewise does not
establish that its local SQLite files implement watching; this decision makes
no claim about that private implementation.

## Options evaluated

| Option | Good fit | Cost or mismatch for this preview |
| --- | --- | --- |
| Agent lifecycle hook | React within an already running turn. | Cannot observe an external event while no turn exists. |
| Call `agent.input()` in a file callback | Tiny demo. | A slow turn blocks observation; no durable receipt or Host session claim. |
| OS file notifications (`watchdog`/Watchman) | Many paths, low latency. | Dependency or daemon, platform edge cases, and a reconciliation path after missed notifications. |
| Fixed-path metadata polling | A few explicit files where a coalesced “changed” signal is enough. | Up to the poll interval of latency; intermediate writes can be coalesced. |
| Host source adapters → durable queue → normal input | Different external sources, restart recovery, continuing sessions. | Adds queue state and an acknowledgement boundary that must be reconciled after a crash. |
| One new subprocess/session per event | Isolated, independent runs, like cloud routines. | Loses the requested continuing conversation and duplicates Host startup work. |

There is no defensible single “most popular” implementation for all event
sources. The repeated design across the official examples is to separate
observation from scheduling a normal agent turn. Source-specific mechanisms
remain source-specific: a file watch, a timer, and a push webhook have
different observation and replay semantics.

## Preview decision

Declare fixed file and timer sources under `watch:` in `.co/host.yaml`; accept
push events with a stable producer event ID through `emit_event()`. A Host
background task observes sources and records a common envelope in a SQLite
queue before delivery. A queue consumer waits for the watch's session to be
idle and calls `input_handler()` with the envelope as a user message. A stable
session ID per watch keeps context across events. The envelope contains ID,
watch, source, observation time, and data; data is framed as untrusted.

SQLite is chosen for *queue state*: atomic insert/dedup, restart recovery,
status inspection, and coordination between Host workers. The Host session
transcript remains in its existing JSONL store. For a few declared files, a
two-second metadata poll is simpler than adding a native watcher dependency;
it explicitly promises a changed-state signal, not every filesystem write.
The existing schedule remains available for ordinary recurring prompts; the
`timer` watch is for a timer event in the common event envelope.

Observation never waits for model work. A busy continuing session retains its
queued event and does not spend a failure attempt. The queue retries delivery
failures up to three times and exposes failed events for manual retry. A
completed Host turn is checked before replaying an unacknowledged event after
a crash. This reduces duplicate turns but cannot promise exactly-once effects
from an agent's external tools. Events from different watches currently share
one consumer: a long turn can delay another watch. This is an explicit preview
limit, to be lifted with per-session dispatch if real workloads require it.
