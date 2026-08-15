# One Browser Boundary

The browser asked ConnectOnion to open Codex. The agent answered as if it had,
but the card showed the base model and the process eventually failed with:

```text
misconfigured: [Errno 2] No such file or directory
```

That error was not one missing executable. It was an architecture diagram
leaking into the product. Two protocol layers and a generic coding-agent edge
could all claim part of discovery, session state, provider launch, approval,
and frontend rendering. A fallback could make the initial response look
successful while losing the provider the user explicitly selected.

## The boundary that users can reason about

The 1.7.0a5 candidate keeps one browser boundary: OIP 0.1. The Python Host owns
the authenticated WebSocket. `@connectonion/react` owns connection and event
state. O Chat renders that state. The same lifecycle carries ordinary agent
messages, Codex activity, Claude Code activity, cancellation, failure, and
reconnect.

Codex and Claude Code remain native backend tools. Each adapter owns the parts
that are genuinely provider-specific: executable discovery, authentication,
sandbox and approval modes, canonical session IDs, native event parsing, and
resume. Each translates a bounded set of tool events into OIP. Neither can
silently become the base model or a generic child.

This means missing-provider errors become boring and useful. They name the
adapter and installation action before a fake session is announced. It also
means browser code does not need another parser every time a coding provider
is added.

## What we measured

The release gate covers OIP Host and WebSocket behavior, exact Codex and Claude
Code session handling, and Codex cards while running, completed, failed,
expanded, and displayed on a phone-sized viewport. The built wheel is installed
in isolation before acceptance, so repository imports cannot make a broken
artifact look healthy.

One protocol does not make provider differences disappear. It puts them on the
backend side of a boundary where approvals, sandboxes, and resume identifiers
can stay explicit. The browser gets one honest stream; the adapter keeps one
honest provider identity.
