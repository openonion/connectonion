# A Channel Is Not a Consumer

The first design for `co feishu listen` was correct, and it was the wrong
thing to build. It put the Feishu listener inside the Host as a lifespan,
gave every sender a `provider:tenant:user` principal, routed that principal
through the trust system, staged events in SQLite, and reserved a change to
how OIP hands out approvals. Every line of it could be defended. It answered
a question nobody was asking.

The question was: who decides what a message is for? In the first design
the channel decided. It knew about Agents, sessions, trust levels and
permission modes, because it had to hand each message to the right one. That
made it heavy, and it made it ours: nothing but a ConnectOnion Agent could be
on the other end.

The second design noticed that and moved the listener out of the Host into
an OIP client with its own key and a three-line allowlist. Nothing in the
Host changed. But the channel still delivered to one consumer, the Agent,
and Claude Code, Codex and a shell script each needed a mode of their own.
Designing consumer modes is how a small tool grows a configuration language.

The third design stopped designing consumers. It turns a message into a
file. `~/.co/feishu/inbox.jsonl` is the log, one JSON line per message,
never deleted. `new/` holds the ones nobody has taken, one file each. Taking
one is `mv new/X cur/X`, which is atomic, so two consumers never take the
same message. Maildir did this for mail in 1995; it needed no library then
and it needs none now.

Once the directory is the interface, the consumers arrive by themselves.
`ls new/` is the unread count. `tail -f inbox.jsonl` is a live view. A shell
loop is two commands, `receive` and `reply`. Claude Code reads it through an
MCP server; `co ai` reads it with `--listen feishu`. The tool knows about
none of them.

Two lessons from the field shaped what the tool keeps for itself. OpenClaw
dedupes inbound messages in a twenty-minute in-memory cache, and during an
LLM outage Telegram redelivered one message about fifty times; every copy
ran when the API came back. So the dedup window here is the log, not a
cache, and a duplicate is dropped after a restart too. OpenClaw also
flattened contact names and group titles into the prompt until someone
showed they carried injected instructions. So the printed message has seven
fields and no provider payload; `raw` stays in the log, opt-in, and never
reaches the queue.

One verb changed name on the way. `wait` was ambiguous about whether it
consumed. `receive` pairs with `send` the way `recv(2)` pairs with
`send(2)`, and everyone already knows it blocks.

The decision is recorded as DD-063. It authorises no Host change, no OIP
change and no framework. It authorises a directory and three verbs, and the
evidence it asks for is the kind a directory can give: fifty deliveries of
one id leave one line; a crash between the write and the acknowledgement
loses nothing; two consumers on one directory never print the same id.
