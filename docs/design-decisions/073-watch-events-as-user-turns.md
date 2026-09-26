# DD-073 — Watch events enter a Host session as user turns

Status: preview implementation for 1.8.9; review with #1499.

## Decision

A Host watches sources declared under `watch:` in `.co/host.yaml`. The first
sources are local file state and a timer. An external producer can use
`emit_event()` to supply a durable event with its own deduplication ID. All
sources place an event envelope in the same queue. A background consumer passes
that envelope to `input_handler()` as a user message, with one persistent
session ID per watch name.

The event envelope contains its ID, watch, source, observation time, and source
data. Source data is framed as untrusted data for the agent. The Host runs a
normal turn; the lifecycle hooks remain about work inside that turn. A watcher
does not wait in `before_iteration` or call the LLM from a file callback.

## Why this shape

An agent cannot act while it has no turn. `before_iteration` can accept input
while an existing turn runs, but it cannot wake an idle agent. The Host already
has the needed turn boundary: its schedule and inbox use `input_handler()`,
which claims a session and records the result. Reusing that path gives watched
events the same session history and failure handling as ordinary input.

Observation and delivery have separate lifetimes. Observing a file or timer
does not wait for a model response. A SQLite queue commits the event before an
agent runs. One OS lock coordinates consumers across Host workers; a worker
death releases it. On recovery, a running event is compared with the durable
session history before retry, so a response saved just before a crash does not
usually cause a second turn. Delivery is retried at most three times, then
reported as failed.

## Alternatives and limits

Calling `agent.input()` directly in a file watcher would leave no persistent
delivery queue and would mix observation with potentially long model work.
Using `core/events.py` would require a turn to exist already. A subprocess per
event would abandon the Host's session and result store.

File observation polls metadata every two seconds. Multiple writes between
polls can be coalesced; this is a signal that the file changed, not a bytewise
change log. A timer coalesces missed intervals after downtime. This preview
does not turn webhooks, peers, or inbox channels into declarations; their
producers can use the same durable event API, and provider replies still need
their own channel routing. The queue gives at-least-once handling after an
uncertain crash; the session-history check reduces duplicate agent turns but
cannot make external tool side effects exactly once.
