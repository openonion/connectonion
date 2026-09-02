# Telegram CLI (`co telegram`)

Send a plain-text Telegram message from the terminal or an agent using a bot
you own. This calls Telegram directly: it does not use OpenOnion credits or an
OpenOnion credential.

## Setup

1. Message [@BotFather](https://t.me/BotFather) in Telegram and create a bot.
2. Put the bot token in your global credential file:

   ```dotenv
   # ~/.co/keys.env
   TELEGRAM_BOT_TOKEN=123456789:your-token
   ```

3. Start a chat with the bot, add it to the destination group, or make it an
   administrator of the destination channel. Telegram will reject a message
   when the bot cannot write there.

The token is a secret. `co status` and `co keys` show whether it was found but
hide its value by default. Use their explicit `--reveal` option only in a
private terminal when you intentionally need the full credential.

## Send from the terminal

```bash
co telegram send 123456789 "The deployment needs attention"
co telegram send @my_channel "Version 1.7 is ready for review"
```

The first argument is a numeric chat ID or a channel username. The command
exits non-zero if setup, transport, or Telegram delivery fails, so scripts can
tell whether the message was accepted.

## Use it as an agent tool

```python
from connectonion import Agent, send_telegram

agent = Agent("operator", tools=[send_telegram])
agent.input("Tell @my_channel that the deployment needs review")
```

Or call it directly:

```python
from connectonion import send_telegram

result = send_telegram("@my_channel", "Deployment complete")
if not result["success"]:
    print(result["error"])
```

Messages are sent as plain text; no HTML or Markdown parse mode is enabled.

## Listen: the bot as a directory of files

The same bot can receive. `co telegram listen` long-polls Telegram with the
same token and writes every message into `~/.co/telegram/`: one line in
`inbox.jsonl` (the log, never deleted) and one file in `new/` (the queue).
Anything that can read a file can answer; the verbs are the same as
[`co feishu`](feishu.md):

```bash
co telegram listen                 # hold the long poll, write the directory; Ctrl-C stops
m=$(co telegram receive)           # block for the next message, take it, print one JSON line
echo "on it" | co telegram reply -100123.55     # quote the message it answers, in its chat
co telegram serve -- claude -p     # one command per message, stdout is the reply
co telegram check | ls | log -f
```

```json
{"id":"-100123.55","chat":"-100123","thread":null,"sender":"4242",
 "text":"@OpsBot look at the deploy","mentioned":true,"at":"2026-09-02T10:31:07Z"}
```

Telegram numbers messages per chat, so the id is `<chat>.<message_id>`.
`thread` is the forum topic when there is one. `mentioned` is true in a private
chat, and in a group when the message @s the bot's username or replies to one
of its messages. With privacy mode on (the BotFather default) a group delivers
only commands and replies to the bot anyway; turn it off with `/setprivacy` and
re-add the bot if you want it to see everything.

`receive` starts a listener if none is running. Telegram keeps unacknowledged
updates for a day, so a listener that was down for an hour catches up; the
mailbox drops anything it has already logged. The full directory layout and
the `serve` contract are in [feishu.md](feishu.md); only the ids differ.
