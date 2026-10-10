---
description: co ai found co linear, then went looking for the key in ~/.co/keys.env, was refused, and gave up on the command. One prompt line says the command will tell you.
tags: [co ai, Prompts, Safety]
---

# The key it went looking for

`co ai` was asked what was open on a Linear board. It did the right thing
first: it read `co --help` and saw `co linear`. Then it did something careful
that turned out to be the wrong kind of careful. Before running the command,
it ran:

```
grep -i linear ~/.co/keys.env ~/.co/*
```

It wanted to know whether a key existed. The approval policy refused the
call, as it should: reading a credential file is never auto-approved. And the
agent, having been told no, concluded that `co linear` was off limits too. It
spent the next twenty calls reading linear.app in a browser.

Nothing in that chain was broken. The policy did its job. The agent was being
cautious. The command was right there. What was missing was one fact the
agent had no way to know: every `co` command that needs a key already checks
for it, and says exactly how to add it when it is missing.

```
$ co linear issues
✗ LINEAR_API_KEY is not set in ~/.co/keys.env. Create a personal API key ...
Next: co env set LINEAR_API_KEY lin_api_... --secret
```

So the cheap way to learn whether a key exists is to run the thing that
needs it. Looking for the key yourself is the expensive way, and here it was
also the refused way.

## One line

`co init` already writes this rule into Codex's and Claude Code's own
instruction files. `co ai`, our own agent, never had it. Its prompt now says:

> **Don't look for credentials yourself; run the command.** Don't read
> `keys.env`, `.env` or token files to see whether a key exists: those reads
> are refused, and the answer is cheaper to get.

A test holds the line in the assembled prompt, so a later rewrite of the
prompt cannot drop it without someone noticing.

The lesson is about refusals. A refusal tells an agent "not this way", and
agents tend to hear "not this goal". The fix isn't to loosen the refusal. It
is to tell the agent about the other way before it goes looking.
