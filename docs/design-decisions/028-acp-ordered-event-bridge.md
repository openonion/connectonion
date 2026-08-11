# Design Decision: Bridge Agent Threads to Ordered ACP Session Updates

**Status:** Accepted
**Date:** 2026-08-10
**Related:** [012 Tool Execution Separation](012-tool-execution-separation.md), [014 Hook System](014-hook-system-design.md), [017 Session Logging and Eval Format](017-session-logging-and-eval-format.md), [025 Interruptible Agent Steps](025-interruptible-agent-steps.md), [026 Structured Turn Outcomes](026-structured-turn-outcomes.md), [027 Wire-only Structured Tool Output](027-wire-only-structured-tool-output.md), [034 ACP-aligned Wire Tool Statuses](034-acp-aligned-wire-tool-statuses.md)

## Decision

ACP event conversion lives in a pure mapper. It converts immutable
ConnectOnion events into the official ACP 0.12 Pydantic models and converts the
canonical `turn_result` into terminal response metadata. It does not own an
event loop, client, Agent, working directory, or transport.

Each ACP session owns a duplex bridge. Starting a prompt creates a monotonically
increasing generation, a bounded FIFO buffer, and an Agent IO lease bound to
that generation. Worker threads take ordered tickets under the bridge's short
serialization condition, deep-copy supported events outside that condition,
then wait for their ticket and buffer capacity before committing. This keeps
slow detachment off the event loop's consume and retirement paths. Only the
empty-to-ready transition is scheduled through `loop.call_soon_threadsafe`.
One async consumer awaits `session_update` calls in FIFO order.
`PromptResponse` is returned only after the consumer reaches the terminal
sentinel and every earlier update has completed.

Finishing or aborting retires the generation. A late tool or provider worker
still holding the old IO lease cannot enqueue into a later prompt. Cancellation
sets the existing interrupt signal and allows the outer Agent turn to emit its
terminal `interrupted` record before normal retirement. Cancelling the async
prompt owner and a failed ACP update both interrupt and retire the generation,
wake blocked producers, settle the worker for a bounded interval, and avoid
leaking private failures into the protocol response.

Protocol `session/cancel` also wakes producers waiting for capacity. Pending
non-terminal events yield so the Agent can observe the interrupt. Each
generation atomically accepts at most one terminal and one final assistant.
Neither is accepted from general Agent IO. After the Agent stops, the adapter
selects the canonical `turn_result` added to the current turn's trace and owns
private enqueue paths for that terminal and, only after a natural or
max-iteration outcome, its final assistant. That terminal, an adapter-owned
answer that already won the completion race, and the single internal sentinel
may exceed the 64-item data buffer during cancellation. This enforces a 67-item
hard bound while allowing the consumer to drain one ordered cancelled or
completed outcome.

## Mapping boundary

- `tool_call` becomes `ToolCallStart` with the existing tool-call ID, required
  title, normalized pending/in-progress status, and structured input.
- `tool_result` becomes `ToolCallProgress` with ACP content objects, completed
  or failed status, and structured output when the SDK can represent it.
- `thinking` becomes `AgentThoughtChunk`.
- a canonical complete `plan` replacement becomes `AgentPlanUpdate`.
- the adapter's final answer becomes one `AgentMessageChunk` with one UUID
  message ID.
- `turn_result` supplies stop reason and measured usage to `PromptResponse`.
- the client-owned user prompt and persistence/control events are not echoed.

Plan is the exception among state-looking events because it is explicit
application state produced by TodoList, not inferred from `session_sync` or tool
output. DD-042 defines its persistence, migration, and authority boundary.

The official SDK serializes optional null fields with `exclude_none`, so a null
tool return keeps its text content but has no `rawOutput` property. The adapter
does not bypass SDK serialization to create a divergent wire shape.

## Why

Agent and tool work is synchronous and may emit from multiple worker threads;
ACP clients are asynchronous and require ordered session updates. Calling the
client from worker threads is invalid, while spawning one task per event loses
ordering, bounded backpressure, and a reliable terminal boundary. Reusing one
buffer across turns also lets abandoned work contaminate a later prompt.

A generation-bound lease makes ownership explicit at the same IO boundary
already used for interruption and approvals. A single consumer preserves the
trace's ordering without changing the simple synchronous Agent API. The
bounded buffer limits queued events for a slow client; synchronous producers
pause until the consumer makes room or retirement wakes them.

## Consequences

Different sessions have independent queues, generations, locks, and Agents.
The existing process-global cwd/stdout lock still serializes the corresponding
critical section. Overlapping prompts for one session fail fast.

ConnectOnion currently receives complete provider responses, so the final
assistant answer is one ACP chunk rather than token streaming. Provider token
streaming can be added later without changing the bridge or terminal drain
contract.

## Rejected alternatives

- **Call `session_update` from the Agent thread:** crosses event-loop ownership
  and cannot apply async backpressure safely.
- **Create one async task per event:** permits reordering and makes completion
  depend on tracking an unbounded task set.
- **Reuse one session queue across turns:** late events can enter the next
  prompt after cancellation.
- **Parse terminal display text:** couples protocol control flow to wording and
  cannot carry measured usage.
- **Bypass the ACP SDK for null raw output:** creates a second, unvalidated wire
  schema beside the pinned official models.
