---
name: wiki-source-whatsapp
description: What is true of WhatsApp chats as a Wiki source — who is speaking, why the agent's own replies are missing, how a group differs from a person, and what a photo in the batch means. Loaded alongside whichever stage Skill is running when the material comes from WhatsApp.
---

# WhatsApp as a source

Why these rules: docs/wiki-skills/wiki-source-whatsapp.md

Read this together with the stage Skill that loaded it. That one says what to
produce; this one says only what is true of **this** source.

## What reaches you

Only the chats the user named with `co wiki sources add whatsapp --chat <id>`.
A person or group missing from the batch was not chosen; never treat it as
absent from the user's life.

Each item carries:

- `role: user` — typed by the account owner: the user's own voice, the most
  important material.
- `role: other` — someone else, with their display name as `speaker`. Keep both
  sides, as with mail.
- `correspondent` / `subject` — the chat id. `…@g.us` is a group;
  `…@s.whatsapp.net` or `…@lid` is one person. A chat id never goes on a page
  as a name.

The agent's own replies are left out on purpose: they are execution, not the
user. If a message refers to "what the bot said", do not reconstruct it.

## A batch is one conversation

Whole chats, oldest first. In a group, write each person's page from what
*they* said, and the group's own page (a project, a client relationship, a
rolling agenda) from what was agreed in it. One page per person across groups,
with each group as a place they were met.

## Groups are clients' rooms

Most business groups are one client each. Never carry a fact, number, price or
guest from one group onto another group's client page, even when the user and
topic are the same. Name the group in the source line of any fact from it.

## Photos, documents and voice notes

`[image saved at /…/media/3EB0….jpg]` is a real local file: open it when it
matters to the page (a contract photo, a floor plan, a screenshot someone asked
about). `[document could not be fetched: …]` means the file is gone: record
that it existed, never guess its content.

## Short messages

"ok", "👍", "done" answer the message before them; read them with it, and never
write a page about a thumbs-up. A short "yes go ahead" from the user after
someone else's proposal is a decision: the proposal is the content, the "yes"
the decision.
