---
description: A Feishu app subscribed to reactions filled the listener's log with "processor not found", once per thumbs-up, retried. The listener now acknowledges reactions and read receipts and drops them.
tags: [Feishu, Inbox]
---

# A thumbs-up is not a question

A contract bot on Feishu answered its messages fine. Its log did not look
fine. Every time someone put a reaction on one of its messages, the SDK wrote
an ERROR line: `processor not found, type: im.message.reaction.created_v1`.
Removing the reaction wrote another one, for `deleted_v1`. Then Feishu, which
had not been told the event was handled, sent it again.

Nothing was broken in the sense of a wrong answer. The bot just had a log
where real errors were hard to find among the reactions.

## How it got there

The app had more subscriptions than our listener knew about. Feishu's console
lets you subscribe to reaction events next to `im.message.receive_v1`, and
apps that use the SDK's outgoing status reactions often already have them.
Our listener registered exactly one handler, for incoming messages. The lark
SDK looks every event up in that table, and an event with no entry is an
exception, which goes back to Feishu as "not delivered".

The workaround on that bot was to remove the reaction subscriptions in the
console, carefully, without taking away the reaction scopes it needed for
sending. That works for one bot, and only for someone who knows which
setting caused the noise.

## The decision

There were two ways to handle these events. One was to make reactions
something the agent can see. The other was to acknowledge them and do
nothing. The issue was clear that a reaction must never trigger an AI reply,
and nobody has asked for an agent that reacts to reactions. So the listener
now registers a handler for reaction created, reaction deleted and read
receipts that does nothing. The SDK finds a processor, Feishu gets its
acknowledgement, and the inbox gets no new message.

The setup docs now name the one event that becomes messages, the three that
are dropped on purpose, and what happens to anything else, so the next person
reading the log knows which of these lines is theirs to fix.

The regression test does not use a fake SDK. It runs the real lark
dispatcher and feeds it the three event types. On the old code the first
one raised the same `processor not found` the bot logged. Now all three are
acknowledged and the inbox stays empty.
