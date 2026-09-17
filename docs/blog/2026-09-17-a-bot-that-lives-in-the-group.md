---
title: A bot that lives in the group
date: 2026-09-17
---

# A bot that lives in the group

Someone types `@` in a WhatsApp group, picks your bot, and asks it something.

Within a second a 👀 appears on their message. Three minutes later — the model
has been thinking, or a script has been running, or someone had to be asked —
the 👀 becomes ✍️. Then the answer arrives, quoted against the question they
asked, in the group where they asked it.

That whole sequence is 1.8.6a2. Three commands, and a number you scan once:

```bash
pip install --pre 'connectonion[whatsapp]'
brew install libmagic
co whatsapp listen                  # scan the QR from the phone, once, ever
co whatsapp consume -- claude -p    # every message that names the bot → a command
```

## Why the group, and not a chat window

Most bots make you come to them. You open a tab, you find the right thread, you
paste in the context they need because they weren't there when it was discussed.

A linked WhatsApp device is in the room. It sees the group the way a person in
it does — including the groups a human made, which the official Cloud API
cannot join at all. When someone says "the price sheet is still wrong" and then
"@bot recalculate", both messages went through the same socket.

Every message becomes a file in a directory:

```
~/.co/inbox/whatsapp/
├── log              every message ever seen, one JSON line each
├── new/             the ones addressed to the bot, waiting
└── outbox/
```

Anything that can read a file can answer it. `consume` hands each one to a
command on stdin and sends whatever it prints back. There is no framework to
learn, because there isn't one — it's a maildir and a shell.

## The part I did not expect to care about

The two emoji.

They started as a courtesy: tell the person their message landed. What they
turned into is the only honest status a bot in a group has ever had.

Before them, everything between "asked" and "answered" rendered as nothing. A
model thinking for four minutes and a listener that had silently died looked
exactly alike from inside the chat, and the only way to tell was to go and read
a log on some machine. Now the question answers itself, and it answers for
everyone standing in the group, not just whoever has ssh:

- no mark — it never arrived
- 👀 and nothing else — it's queued, nothing picked it up
- ✍️ with no answer — the reply failed

That is a debugger made of two characters, running in the same window as the
conversation, for free.

## Local models, if you want them

```python
agent = Agent("desk", model="ollama/qwen3.5:9b", tools=[check_stock])
```

No key, no credits, nothing leaving the laptop. Tool calls and structured
output both work — we run the acceptance against an installed wheel with every
cloud credential stripped from the environment and an empty `HOME`, so "it
worked" cannot quietly have been a cloud call. Any other local runtime — LM
Studio, vLLM, an internal gateway — is an explicit `base_url` away.

## Mail, for the same agent

The bot in your group and the one reading your mail are the same agent, and the
mail side got sharper this release:

```bash
co outlook inbox --since 7d --json      # a window, machine-readable
co outlook reply 3 "Signed copy attached" --attach signed.pdf
co outlook send a@b.com "Invoice" "Attached" --at +2h
```

`--at` holds the message and sends it when the time comes — verified this week
by scheduling one two minutes out and watching it arrive twenty-three seconds
after its slot, not immediately, not never.

## Where this is

Preview. `pip install --pre connectonion`; a plain install stays on stable
1.8.5. WhatsApp is a linked companion device, which means a number dedicated to
this and never a personal one — that constraint is real and it is in the docs.

What it can't do yet is written down too, in the release notes rather than
discovered later: a photo arrives with an empty body, a consumer is handed one
message rather than the conversation around it, and the calendar's full journey
hasn't been run end to end against a real account.

The release notes are `docs/releases/1.8.6a2.md`. The acceptance run — every
gate, every timestamp, and the three defects it found — is
`docs/acceptance/1.8.6/whatsapp-live-2026-09-17.md`, because a release that
claims a group integration should show its working.
