---
title: The reminder Mistral refused
date: 2026-10-30
description: A marker that hides a reminder from the chat was travelling in the request, and Mistral rejected the retry.
---

A migration plan ran long enough that Mistral stopped at its output limit.
The agent did what it is supposed to do with a cut-off answer: throw the
half-plan away, tell the model it was discarded, and ask for a shorter one.
The second request never got an answer. Mistral sent back 422, `Extra inputs
are not permitted`.

The extra field was `internal`. It is how the chat knows a
`<system-reminder>` is context about the turn, not something the person
typed, so the raw tags do not show up as a bubble. The session is supposed
to keep that mark. The provider is supposed to see a plain user message.

The copy that builds a provider request already knew this kind of field
existed. It left `id` behind, because an id is ours. `internal` arrived
later, for the chat, and a watch turn added `watch_event`. The copy never
learned their names. Anthropic never showed the bug, because it rebuilds a
message from role and content before it sends anything. A provider that
ignores unknown keys never showed it either. Mistral validates the object,
so the retry, a file-upload notice, and an empty-answer reminder all died
on the same field.

The session message is unchanged. The copy that leaves drops those session
keys, and a tool call's own id stays, because that one belongs to the
provider. The test that failed first is the retry whose last message was
`content`, `internal`, and `role`.

A key that exists so our UI can tell two user messages apart is not part of
the conversation we send.
