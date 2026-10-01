# From the inbox to the room

`co slack` shipped in 1.8.9 as an inbox. A listener holds a Socket Mode
connection, and every message addressed to the bot becomes a file. That covers
"answer whoever asks", but the first question people wanted an agent to answer
was a different one: what did #ops say about the deploy this morning? The
inbox cannot answer it. It only has what arrived while a listener ran, and only
what was said to the bot or where it listens. The conversation happened before
anyone was listening.

The plan in #2051 was to read through Slack's official MCP server, which went
GA in February with search, history and threads built in. That fell through on
one line of Slack's terms: unlisted apps are prohibited from using MCP. It
admits directory-published apps, or internal ones with a fixed app id and a
workspace admin's approval. A CLI that every user points at their own app
cannot be either. The Web API underneath has no such gate. `conversations.list`,
`.history` and `.replies` take the same bot token the inbox already holds, so
`channels`, `history` and `thread` needed no new credential at all.

Search was the exception. `search.messages` refuses bot tokens outright,
because it searches as a person and sees what that person can see. So
`co slack search` reads an optional `SLACK_USER_TOKEN`. When the token is
missing it does not quietly fall back to something weaker. It exits 1 and
names the token, the scope and the command that adds it.

Writing the help pages turned up a smaller problem. The natural example was
`co slack history #ops`, and in bash an unquoted `#` starts a comment. The
command an agent would copy reads the channel list instead, with no error at
all. The verbs take a bare `ops`, and the help and the skill say to quote
`'#ops'`.

Setup had the same shape of problem. The 1.8.9 page was seven steps across
five screens of Slack's app settings. Each new scope added another step, and a
missed one did not fail until the first real message. A Slack app manifest
holds all of it in one document: Socket Mode, the event subscriptions, the
Messages tab, every bot scope, and `search:read` for the user token.
`co auth slack` prints a link that opens Slack with that manifest filled in.
The person then clicks Create and Install, and makes the one app-level token a
manifest cannot make. Each token is pasted at a hidden prompt rather than
passed as an argument, so it never sits in shell history. Each is checked with
Slack before anything is saved, and the scopes it lacks are read from the
`x-oauth-scopes` header Slack returns.

Every test passed against a fake Slack, and the first run on a real
workspace still found three things the fake could not. Search failed on an
ordinary user token: it asked for `users:read` to name the authors, a scope
the user token had no reason to hold. The bot token already has that scope,
so names now come from the bot, and the user token needs nothing beyond
`search:read`. In a pipe, which is how every agent reads a command, the
`Next:` line printed before the results. It went to stderr while the rows
were still waiting in stdout's buffer. The handler now prints it after the
results. And one reply was shown as "(1 replies)".

The same run settled the manifest question. The link really does open
Slack's "Create from a manifest" dialog already filled in, though the form has
two steps, Next and then Create, where the first draft of the instructions
said one. The inbox's own listen-and-reply gates have still not run on a real
workspace, so the "Experimental" label stays.
