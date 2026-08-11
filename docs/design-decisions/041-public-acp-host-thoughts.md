# DD-041: ACP Host thoughts mirror only persisted application text

**Status:** Accepted

**Date:** 2026-08-12

**Related:** [028 Ordered ACP Event Bridge](028-acp-ordered-event-bridge.md), [035 Versioned ACP Host Carrier](035-versioned-acp-host-carrier.md), [036 Stable ACP Agent Message Identity](036-stable-acp-agent-message-identity.md)

## Context

The local stdio ACP adapter already maps ConnectOnion `thinking` events to
`AgentThoughtChunk`. The authenticated network Host still sends only the legacy
event. Its event vocabulary also contains `llm_call` and `llm_result`, which are
provider/status diagnostics rather than text the application chose to show.

The active browser path is Host -> `@connectonion/react` -> O Chat. React owns
the protocol reader and O Chat renders normalized `ChatItem` state. The
standalone TypeScript SDK is retired.

## Decision

The Host maps only a canonical event with `type=thinking`, a non-empty persisted
event ID, and non-empty string content to the official ACP v1.19
`AgentThoughtChunk`. `Agent._record_trace()` already assigns a UUID before it
persists and streams these events, so the same domain identity becomes ACP
`messageId` and the replayed `thinking` ChatItem ID.

Persistence provenance is transport-local, not a client-controlled JSON field.
`Agent._record_trace()` uses an internal IO path that queues a private dictionary
subtype in `WebSocketIO`; ordinary `agent.io.send()` events remain plain
dictionaries. The Host requires that provenance before mirroring `thinking`,
and both objects serialize to the same legacy JSON shape. This prevents an
ordinary direct `send({"type": "thinking", ...})` from being misclassified as
an ACP thought while preserving provenance when the outgoing log is replayed.

This is a cooperative in-process API boundary, not a Python sandbox. Extensions
running inside the Agent process are trusted code: they can import private
objects, call private methods, or mutate the Agent directly. Isolating hostile
plugins requires a separate process/capability boundary and is outside this
carrier decision.

Known `re_act` and `reflect` producers explicitly create application text and
already expose it to the same authenticated browser in the legacy event and
session replay. This slice does not inspect or infer model reasoning. It never
maps `llm_call`, `llm_result`, raw provider responses, system prompts, debug
payloads, content-free busy indicators, or arbitrary trace entries.

One complete persisted thought becomes one ACP text chunk. This Host carrier
does not claim provider token streaming. ACP gives chunks message identity but
no sequence or offset, so browser accumulation cannot distinguish repeated
text from retransmission. A future streaming design must define generation,
ordering, resume, and replay rather than adding hidden client state.

If the canonical thought has a non-empty string `kind`, the adapter carries it
as `_meta.connectonion.kind`. This is a presentation hint only. Invalid hints
are omitted without discarding otherwise valid public content, and `_meta`
never affects authority, persistence, ordering, or execution.

The Host sends the additive ACP notification immediately before the matching
legacy thought event. The React reader lands first, validates active-session
ownership, and upserts ACP, legacy, and replay by the persisted ID. O Chat does
not parse ACP. A malformed mirror is logged and skipped while the legacy event
and authoritative `OUTPUT` continue, so presentation conversion cannot invite
a retry of completed work.

## Privacy and trust boundary

ACP's generic thought field can contain internal reasoning. React cannot
classify text origin, and this decision does not claim otherwise. The narrower
ConnectOnion Host writer contract is what limits this carrier to persisted,
already-visible application text. A different ACP agent or Host defines its own
privacy contract.

## Compatibility and rollback

Canonical traces and session snapshots remain unchanged. Updated React readers
de-duplicate the additive frame; older clients keep the legacy event. The
Python compatibility client ignores unsupported ACP thought updates and then
renders the legacy twin, so it does not duplicate UI during rollout.

Rollback removes `thinking` from the Host mirror whitelist and the pure mapper.
No stored session, provider input, authentication state, or O Chat code needs a
migration or downgrade. Removing the legacy event remains a separate major-
version decision backed by usage evidence.

## Rejected alternatives

- **Map `llm_call` or `llm_result`:** status and usage diagnostics are not
  application-authored thought content and may expose provider internals.
- **Read provider responses or traces to find reasoning:** expands the privacy
  surface and bypasses the explicit public event boundary.
- **Generate `messageId` in the adapter:** breaks ACP/legacy/replay identity.
- **Accumulate arbitrary chunks in React:** without chunk identity or a resume
  generation, retransmission and repeated content are indistinguishable.
- **Store ACP envelopes in trace:** couples canonical persistence to one
  transport and makes rollback destructive.
- **Trust a JSON provenance flag:** any direct IO caller could forge the flag,
  and an internal transport concern would leak onto the public wire.
