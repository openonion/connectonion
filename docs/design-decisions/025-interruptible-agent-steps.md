# Design Decision: Interrupt Blocking Agent Steps by Abandonment

**Status:** Accepted
**Date:** 2026-08-10
**Related:** [012 Tool Execution Separation](012-tool-execution-separation.md), [018 Event API Naming](018-event-api-naming.md), [019 Agent Lifecycle](019-agent-lifecycle-design.md)

## Decision

Hosted agents run each blocking LLM completion and tool invocation on a
disposable daemon thread. The agent thread polls the selective IO mailbox for
`INTERRUPT` every 200ms. When a signal arrives, the agent abandons the worker's
result and exits through the existing `stop_signal` lifecycle.

Agent-injected tools receive a shallow per-invocation Agent view: its session is
pinned to the interrupted turn and its IO is a revocable receiver lease. The
lease stops late sends and returns an interrupt without consuming a future
mailbox response. Custom IO adapters without cancellable receive support keep
graceful boundary stopping for agent-injected tools.

Blocking approval and question gates recognize the same signal explicitly.
Completed work wins a same-window race: after each timed join, worker completion
is checked before the mailbox is drained.

## Why

The original graceful stop from #188 checked only at iteration boundaries. A
slow provider request or tool could therefore make the Stop button appear
unresponsive for seconds or minutes. There is no safe general-purpose way to
terminate arbitrary Python code, and provider streaming would change every LLM
implementation without solving non-cooperative tools.

Abandonment keeps one provider-independent mechanism at the two blocking call
sites. It also preserves the established lifecycle and message rules:

- interrupted LLM output is never appended;
- an interrupted tool batch still receives one result per tool-call ID;
- `on_stop_signal`, persistence, and the normal output contract remain intact;
- non-INTERRUPT mailbox messages are not consumed.

## Consequences

Stop latency is bounded by the polling interval plus scheduling overhead, not
by the duration of the provider or tool call. Local agents without hosted IO
keep the direct call path and pay no thread overhead.

The abandoned worker may continue consuming provider tokens or completing tool
side effects. Agent-injected tools can retain an agent reference, so the
guarantee is deliberately narrow: ConnectOnion does not commit a late return
value to messages or trace. Tools requiring stronger semantics must implement
cooperative cancellation or isolate killable work in a subprocess.

## Rejected alternatives

- **Asynchronous exception injection or process signals:** unsafe around locks
  and ineffective for many blocking socket calls.
- **Streaming every provider in this change:** a much larger compatibility
  surface and still no answer for arbitrary tools.
- **A second “force stop” stage:** both clicks would have identical abandonment
  semantics, so the extra state would mislead users.
- **Draining the whole mailbox:** would steal approvals, mode changes, and
  runtime messages unrelated to stopping.
