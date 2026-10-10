---
description: co handoff 1.9.2b7: the recipient gets one block to paste into Codex, their agent does the rest, and the sender learns it arrived.
tags: [Handoff, Codex, Experimental]
---

# Paste this into Codex

The first preview of `co handoff` asked the person receiving a handoff to run
`co handoff inbox`, find an id, run `co handoff show` with that id, then
`co handoff open`. Every step worked in testing. The owner read it and asked who
this was for. A teammate who already lives in a terminal might follow it. Someone
whose colleague just forwarded them "the login task" would not, and should not
have to.

So the mail is now one thing: a block headed **Paste this into Codex or Claude
Code**. It holds the whole brief, so it works even if the person never installs
anything, and five short steps addressed to their agent: install co if it is
missing, save the brief, run `co handoff accept <code>`, tell the person what the
task is and ask before changing anything, and send questions back with
`co handoff ask`. The person pastes it into Codex, and that is all they do.

## The sender finds out

Before, "sent" was the last thing the sender knew. Now the acceptance comes back
over the same agent mail, carrying the recipient agent's address, and
`co handoff status` says "Accepted by 0x… at 20:52". Questions the brief could
not answer arrive on the same handoff, `co handoff answer` replies, and a
running `co ai` prints both as they come in.

## Three things the real runs broke

We sent seven handoffs between a Mac and a Linux box, and had each recipient's
Codex take the prompt exactly as it arrived in the mail.

**The mail service flattened the prompt.** It sends every body as HTML, so the
line breaks were gone and the five steps arrived as one paragraph. The prompt now
goes in `<pre>`, and the terminal reader `co email read` stops wrapping long lines
too, which had been cutting the code in half.

**An agent retyped the code and got one character wrong.** The first code was
300 characters of base64 JSON. One wrong letter still decoded, and it turned
`openonion.ai` into `openonion.as`: the acceptance went to a mailbox that does
not exist. The code is now about 110 characters and ends in a checksum, so a typo
is refused and nothing is sent.

**`pip install connectonion` installs the wrong thing.** On a machine without co,
Codex followed the install step exactly and got the last stable release, which
has no `handoff accept`. The step now asks for at least the sender's own version,
which lets pip take a preview without `--pre`. With that, a clean home directory went from no co to accepted in 83
seconds, with no signup. `co init --yes` created the identity and its mailbox.

## What the code is not

The code lets one agent accept one handoff and ask about it. It is not an invite
code. An invite holder becomes a contact, and a contact may run commands on the
sender's host; a handoff mail can be forwarded to anyone. So the agent that
accepts is recorded only as a handoff-scoped peer, never in the trust lists, and
a test checks that the code gets nothing from the trust rules.

Try it: `co handoff send <who> "<what>"`. The recipient only needs to paste.
