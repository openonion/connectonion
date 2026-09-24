---
name: wiki-source-whatsapp
description: What is true of WhatsApp chats as a Wiki source — who is speaking, why the agent's own replies are missing, how a group differs from a person, and what a photo in the batch means. Loaded alongside whichever stage Skill is running when the material comes from WhatsApp.
---

# WhatsApp as a source

Read this together with the stage Skill that loaded it. That one says what to
produce; this one says only what is true of **this** source.

## What reaches you

Only the chats the user named with `co wiki sources add whatsapp --chat <id>`.
The phone is in many more groups — family, unrelated communities, other
clients — and none of them is in the batch. So a person or a group that is not
here is not "absent from the user's life"; it was not chosen.

Each item carries:

- `role: user` — something the account owner typed on their own phone. This is
  the user's own voice, the most important material in the batch.
- `role: other` — someone else in the chat, with their display name as
  `speaker`. Keep both sides, as with mail: the other side is a person.
- `correspondent` / `subject` — the chat id. `…@g.us` is a group;
  `…@s.whatsapp.net` or `…@lid` is one person. A chat id is not a name and
  never goes on a page as one.

The agent's own replies are left out on purpose. When the user's assistant
answered in the chat, that answer is execution, not the user — the same rule as
coding sessions. If a message in the batch refers to "what the bot said", the
bot's words are not here; do not reconstruct them.

## A batch is one conversation

A batch holds whole chats, oldest chat first. A group chat is many people at
once: write each person's page from what *they* said, and the group's own page
(a project, a client relationship, a rolling agenda) from what was agreed in it.
The same person can appear in several groups; one page for them, with each
group as a place they were met.

## Groups are clients' rooms

Most business WhatsApp groups are one client each. Never carry a fact from one
group onto a page about another group's client, and never put one client's
numbers, prices or guests on another client's page — even when the user is the
same and the topic is the same. When a fact came from a group, say which one in
its source line.

## Photos, documents and voice notes

A media message arrives as its text plus a line such as
`[image saved at /…/media/3EB0….jpg]`. That is a real file on this machine:
open it when it matters to the page — a contract photo, a floor plan, a
screenshot someone asked about. `[document could not be fetched: …]` means the
file is gone; record that it existed, never guess what it said.

## Short messages

WhatsApp is terse. "ok", "👍", "done" answer the message before them; read them
with it, and do not write a page about a thumbs-up. A decision in WhatsApp is
often a short "yes go ahead" from the user after a longer proposal from someone
else — the proposal is the content, the user's "yes" is the decision.
