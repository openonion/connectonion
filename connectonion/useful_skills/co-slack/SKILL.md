---
name: co-slack
description: Read and answer Slack with `co slack` — what a channel said, a thread, a search across the workspace, and a reply in the right thread. Use for "what did #ops say today", "find the message about X and reply in its thread", "is the Slack bot set up", or any Slack channel, thread or message the user names. Experimental; routes to `co slack --help`.
---

# Slack

`co slack` is the user's own Slack app. Read verbs ask Slack directly (Web API);
inbox verbs (`listen`, `receive`, `reply`) only see what arrived while a
listener ran. It is experimental: not yet run on a live workspace.

**Read the help before the first command**, and read every output, not just
the exit code:

```bash
co slack --help                 # every verb; the "Read the workspace" panel is channels, history, thread, search
co slack <verb> --help          # flags and an example for that verb
```

## Which command

| the user wants | run |
|---|---|
| set it up, or fix a token | `co auth slack` |
| know whether it works | `co slack check` |
| which channels exist (ids, names) | `co slack channels` |
| what a channel said | `co slack history ops -n 50` |
| a whole conversation under a message | `co slack thread <channel>:<ts>` |
| find a message by its words | `co slack search "words" --in ops --from alice` |
| answer in a message's thread | `co slack send <channel> "text" --reply-to <channel>:<ts>` |

Add `--json` to any read verb for one object per line: `id`, `chat`, `thread`,
`at` (UTC), `sender`, `sender_name`, `text`, and `replies` (history and thread).

## "What did #ops say today?"

1. `co slack history ops -n 100 --json` (a name, or `'#ops'` quoted: an
   unquoted `#` is a shell comment).
2. Keep the messages whose `at` falls on today in the user's timezone; the
   plain view already prints local time.
3. For any message with `replies` > 0 that matters, `co slack thread <id>`.
4. Answer from what was said, citing who said it. Do not post anything.

## "Find the message about X and reply in its thread"

1. `co slack search "X" -n 10` (narrow with `--in` / `--from`). Without
   `SLACK_USER_TOKEN` it exits 1 and says so: fall back to
   `co slack history <channel>` on the likely channel, or tell the user to run
   `co auth slack` and paste the User OAuth Token.
2. Read the thread before answering: `co slack thread <id>`.
3. Show the user the reply and get their yes. Then
   `co slack send <channel> "reply" --reply-to <id>`, using that message's
   `chat` and `id`. It prints the new message's id.

`co slack reply <id>` is for messages the inbox received; for an id from
`history`, `thread` or `search`, use `send --reply-to`.

## When it refuses

Every refusal ends with `Next:` and the command to run. The common ones:
`not_in_channel` (invite the bot: `/invite @<bot>` in Slack), `missing_scope`
(the error names the scope; the user adds it and reinstalls the app), and a
rejected token (`co auth slack`). Do not retry a refusal unchanged.
