# DD-036: Persist Domain Identity for ACP Agent Messages

**Status:** Accepted
**Date:** 2026-08-11
**Related:** [028 Ordered ACP Event Bridge](028-acp-ordered-event-bridge.md), [035 Versioned ACP Host Carrier](035-versioned-acp-host-carrier.md)

## Decision

Every new terminal assistant message receives a UUID when it is added to the
canonical session. This ID is transport-neutral message identity: session
reconstruction uses it as the agent `ChatItem.id`, and the ACP adapter uses the
same value as `agent_message_chunk.messageId`.

The ID is persistence and presentation metadata, not provider input. Every
provider entry point that reuses canonical history, including debug previews,
uses one shared sanitizer to build a detached list without top-level message
IDs. Tool-call IDs nested inside provider messages are unaffected.

Legacy stored messages remain readable. `session_to_chat_items()` retains its
index fallback for messages without IDs, but the Host emits no ACP agent-message
mirror for such a message. The existing `OUTPUT` remains authoritative, and a
new answer added to a restored session receives a stable ID normally.

One complete, non-empty, persisted assistant answer is serialized as one ACP
v1.19 text chunk immediately before `OUTPUT`. The final stored message must
carry a non-empty ID and have content exactly equal to `OUTPUT.result`. The live
forwarding loop mirrors only tool lifecycle events; plugin or arbitrary
`assistant` events cannot become ACP agent messages.

This carrier profile does not promise provider token streaming. DD-028 already
established that a complete provider response may be one ACP message chunk. A
future streaming design must define chunk ordering and replay independently.

`@connectonion/react` owns browser decoding, verifies that the ACP carrier's
session ID matches its active session, and upserts by the preserved message ID.
oo-chat renders the SDK's `ChatItem` and does not parse ACP. The standalone
TypeScript SDK is not part of the frontend rollout.

## Compatibility and failure behavior

The message notification is additive. `OUTPUT.result`, session, and chat items
remain unchanged and authoritative. Older clients keep their current
completion path; updated React clients converge ACP and the authoritative
snapshot on one stable card.

Empty text, synthetic terminal notices, legacy messages without IDs, mismatched
results, and conversion failures produce no ACP message notification. The
legacy `OUTPUT` still drains, so presentation conversion cannot make completed
work look retryable.

## Rollback

Stop emitting the additive notification and stop assigning IDs to new terminal
messages. Existing IDs are inert metadata and remain hidden from providers, so
stored sessions need no migration or downgrade.

## Rejected alternatives

- **Use `msg-{message index}`:** auto-compaction rewrites the message array, so
  later answers can reuse an old ID and overwrite an existing browser card.
- **Generate an ID only in the ACP adapter:** reconnect would produce a second
  identity for the same stored answer.
- **Persist an ACP-specific field:** couples canonical storage to one protocol;
  a generic domain message ID is reusable by every transport and UI.
- **Derive identity from content hashes:** identical answers in different turns
  are different messages, and content is not a safe identity boundary.
- **Treat every terminal result string as an agent message:** max-iteration and
  other synthetic outcomes are not persisted assistant speech.
