---
description: co mcp calls the connectors a user already enabled in Codex, Gmail included, without a second login and without a model turn. Claude Code's connectors could not be reached the same way, and why we did not force it.
tags: [MCP, Codex, Onboarding]
---

# The login you already have

The first thing co rem asks of a new user is to connect their mail. For
someone who arrived from an ad, that is a second login for an account they
had already connected that morning, in Codex or in Claude.

So we asked a narrower question: can `co` use the connection that is already
there?

Codex answered first. Its app-server protocol, the one co already drives to
run Codex as a coding harness, has a method called `mcpServer/tool/call`. It
takes a session id, a server and a tool. A session can be started empty and
marked ephemeral: no model turn, nothing written to the user's history. On
the owner's Mac the account connectors came back as one server,
`codex_apps`, with 537 tools. A Gmail search answered in 1.3 seconds with
message ids and thread ids, which is everything a page needs to cite a mail.

Claude Code took longer to answer, and the answer was no. Its claude.ai
connectors go through a proxy authorised by the user's own Claude login. The
only way to call it without Claude would be to take that login's token and
use it from another program, and that would be co pretending to be Claude
Code with someone else's credentials. `claude mcp serve` exposes Claude
Code's own tools, not the connectors. The supported path is a Claude turn,
measured at 12 seconds and four cents for one search: fine for a question,
not a way to read two years of mail.

So `co mcp` is three commands on top of Codex: `ls`, `tools`, `call`. Each
tool already says whether it only reads. A read-only tool runs and prints its
own data. Anything else (send, delete, create) prints what it would do and
waits for `--yes`, because a connector acts as the user, and a command an
agent can run should not send mail on a guess.

The lesson is in the order of the questions. We started from "connect your
mailbox" as a step everyone takes. The better first question is "what can
this person's tools already do". Here the answer was most of it.
