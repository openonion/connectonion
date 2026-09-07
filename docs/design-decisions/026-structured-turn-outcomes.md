# Design Decision: Record One Structured Outcome Per Agent Turn

**Status:** Accepted
**Date:** 2026-08-10
**Related:** [017 Session Logging and Eval Format](017-session-logging-and-eval-format.md), [019 Agent Lifecycle](019-agent-lifecycle-design.md), [025 Interruptible Agent Steps](025-interruptible-agent-steps.md)

## Decision

Every attempted Agent turn records one terminal `turn_result` trace entry after
its lifecycle handlers finish. The entry identifies the turn and one
provider-neutral reason: `natural`, `max_iterations`, `interrupted`, `stopped`,
or `error`. `interrupted` is reserved for a real client interrupt; policy
rejection, approval feedback, and progress checkpoints are `stopped`. Errors
include only their Python type, not their message.

The entry also contains the usage measured by `llm_result` entries created in
that turn. Input, output, cache-read, cache-write, explicit provider total, and
cost values are summed independently. An explicit provider total wins for its
call; otherwise that call contributes input plus output. Missing usage remains
`null`, and unlabelled reasoning tokens are never invented.

`Agent.input()` continues returning the same string as before. User-facing
completion and maximum-iteration text remains presentation, not a protocol
contract. Adapters consume `turn_result` instead of parsing those strings.

## Why

Sessions contain multiple turns and a turn may make multiple LLM calls. The
Agent already records each call's measured usage, but consumers had no
unambiguous boundary or terminal reason. Inferring either from the last string
mixes presentation with control flow and can accidentally count restored
history.

The trace is already the ordered, JSON-compatible source shared by local
logging and hosted IO. A terminal trace entry keeps that single source of truth
without changing the simple string API.

## Consequences

The turn boundary begins after a valid session shape exists and before logging
setup, message/file preprocessing, lifecycle hooks, or model work. Failures in
any of those turn stages record an error outcome and re-raise the original
exception. Logging and console rendering after the terminal entry remain
downstream and do not redefine whether the Agent work completed.

Consumers can map the neutral reason into their own protocol. For OIP,
`natural` remains a successful completion, `max_iterations` is an iteration
limit, and a client `interrupted` becomes cancelled. The adapter maps `stopped` according
to its approval/refusal policy rather than misreporting it as cancellation.

## Rejected alternatives

- **Parse returned text:** wording is presentation and changes independently.
- **Read cumulative Agent counters:** they include earlier turns and cannot
  reconcile provider-reported totals.
- **Return a new result object from `Agent.input()`:** breaks the two-line API
  and every existing string consumer for data already available in the trace.
- **Copy exception messages into the outcome:** provider and tool errors may
  contain credentials or private request data.
