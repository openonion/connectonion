---
description: co handoff (experimental): say "hand this to Ody" in Codex, and Ody's Codex continues with the decisions, the rejected options and the discussion itself.
tags: [Handoff, Codex, Experimental]
---

# "Hand this to Ody"

The expensive part of passing a task on is not the task. It is the afternoon
of discussion behind it: we compared two ways to store the login token, threw
one out for a reason that mattered, and agreed the next step. Hand that to a
colleague and you write it all down again, or they ask you again, or they pick
the option you already rejected.

The discussion already exists. It is sitting in Codex's session file. So
`co handoff send ody` reads the end of the session you are in, makes one
model call to pull out the goal, each decision with the options that lost and
why, where things stand, the next step and the open questions, and keeps the
last forty turns of the conversation verbatim as evidence.

Then it stops and shows you everything that would leave the machine. Not a
summary of it: the recipient, the decisions and the full excerpt. Nothing is
sent until you say so, and what you say yes to is a file with a content hash;
the copy that arrives carries the same hash. A bundle with anything that looks
like a key or token in it is refused.

On the other side, Ody runs `co handoff inbox`, reads the summary, and
`co handoff open` starts a Codex session on his machine that has already read
the handoff. We asked that session the question a new owner always asks:

> why did we reject option B?

> Decision 1 says Option B used in-process retries with `asyncio` sleep.
> Because the application deploys several times a day, restarts would lose
> pending retries. The durable Redis queue preserves them across restarts.

That was a second machine, a different Codex login, and nobody had typed the
reason anywhere except in the original discussion.

## What we learned building it

**The agent found the command on its own.** With ConnectOnion's command index in
`~/.codex/AGENTS.md`, a fresh Codex given only "hand the task we just discussed
to aaron.xie@mail.openonion.ai" ran `co handoff --help`, then
`co handoff send`. Without the right `co` on its PATH it did something worse:
it fell back to scheduling an Outlook email from the owner's own account. The
index is what turns "hand off" into the right command instead of an improvised
one.

**It also approved its own preview.** The same run read the preview and sent it
with `--yes` in the next breath. We changed the preview to say, in words the
agent reads, "stop here and ask the person", and ran it again. It sent anyway:
being asked to hand something off reads, to an agent, like permission to send
whatever it drafted. Text cannot be the gate for the thing reading the text.
Today the gate is the coding client's own command approval; a person-only
approval is the next piece of work, the same rule as #2353's discover switch.

**Long sessions forget, but the file does not.** A real Claude Code session
compacts itself; its jsonl keeps a plaintext summary row, so the brief starts
there. Codex compacts too, but its summary is encrypted on disk: in 107
compactions on one Mac, not one was readable. What Codex does keep in the clear
is the user's own earlier messages, and that is what the draft reads before
the turns that followed.

**Eight runs, two machines, both directions.** Every run asked the opened
session "why not option B?" and two other things only the brief knew. 24 of 24
answers came from the handoff. Most of the fixes were small and about reading:
the recipient's address hidden behind "no addresses owned yet", a send that
reprinted the whole preview, a sender shown as a bare mailbox.

**Mail is a fine first wire.** Every co identity already has a mailbox,
delivery works while the recipient's laptop is closed, and nothing has to be
running. The transport is two small functions, so a direct agent-to-agent
route can replace it later without touching anything else.

Try it: `co handoff --help`. It is experimental; tell us where it breaks.
