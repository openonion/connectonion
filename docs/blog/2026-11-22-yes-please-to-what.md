---
description: A WhatsApp reply like "Yes please" reached the agent without the message it answered, so the agent guessed, and on 11-17 it guessed the wrong video. Every inbox line now says what a reply, reaction or edit points at, next to its text.
tags: [Inbox, WhatsApp, Agents]
---

# "Yes please" — to what?

In a group, people reply to a specific message: "yes please", "the first one",
"no, test it yourself". On the phone the quote sits right above the words. The
agent only had the words.

The reference was always stored. Every reply carried `quoted` with the id, the
sender and the text it answers. But agents read `text`, and `quoted` was one
more field down the line. On 2026-11-17 a reply about a cover image was read
as being about another video. On 2026-11-20 "Yes please" had to be resolved
by hand.

Now the answer sits next to the question:

```json
{"text":"Yes please","reply_to":"↩ replying to you: \"Cover for the launch video, v2\" (id 3EB0COVER)", …}
```

- `receive`, `log` and `consume` all show it, on WhatsApp, Telegram and
  Discord alike.
- `you` means the quoted message is one of yours, so you can tell that someone
  is answering the bot.
- A WhatsApp reaction says what it is on: `↩ reacting to`, followed by that
  message's own text from your log.
- `co whatsapp log` adds the line to replies stored before this change.
- A message that quotes nothing has no `reply_to`, and its line is
  byte-for-byte what it was.
