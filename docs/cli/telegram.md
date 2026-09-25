# Telegram CLI (`co telegram`)

> **`send` is stable; `listen`, `receive`, `reply`, `done` and `consume` are experimental** — tested against fakes, not yet a live bot. Edit, delete and react are not implemented and say so.

Send a plain-text Telegram message from the terminal or an agent using a bot
you own, and receive what people send it as a directory of files. This calls Telegram directly: it does not use OpenOnion credits or an
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

The first argument is a numeric chat ID or a channel username. Group and
channel ids start with `-` (`-100123`) and are taken as ids, not options. The
command exits 3 when no token is set, and 1 with Telegram's reason and
`Next: co telegram check` when Telegram refuses, so scripts can tell whether
the message was accepted.

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

The same bot can receive. `co telegram listen` long-polls Telegram's
`getUpdates` with the same token and writes every message into
`~/.co/inbox/telegram/`: one line in `received.jsonl` (the log, never deleted)
and one file in `new/` (the queue). Anything that can read a file can answer.
The verbs are the same as [`co feishu`](feishu.md), and `send` above stays
exactly as it was:

```bash
co telegram check                  # token, listener, connection, unread count
co telegram listen                 # hold the long poll, write the directory; Ctrl-C stops
co telegram receive                # block for the next message, take it, print one JSON line
echo "on it" | co telegram reply -100123.55   # quotes the message it answers, in its chat
co telegram done -100123.55        # took it, decided not to answer
co telegram consume -- claude -p   # one command per message, stdout is the reply
co telegram ls                     # what is waiting
co telegram chats                  # which conversations exist
co telegram log -f                 # everything, as it arrives
```

```json
{"id":"-100123.55","chat":"-100123","thread":null,"sender":"4242","sender_name":"Aaron Xi",
 "text":"@OpsBot look at the deploy","kind":"text","quoted":null,"mentioned":true,
 "at":"2026-09-02T10:31:07Z"}
```

- **The id is `<chat>.<message_id>`.** Telegram numbers messages per chat, so
  a bare `55` from a second group would have been dropped as a duplicate of the
  first. `reply` parses the id back into the quote Telegram wants.
- **`thread`** is the forum topic when the group has topics, else `null`.
- **`mentioned`** is true in a private chat, and in a group when the message
  @s the bot's username, is a `/command@YourBot`, or replies to one of the
  bot's own messages. With privacy mode on (the BotFather default) a group
  delivers only commands, @mentions and replies to the bot anyway; turn it off
  with `/setprivacy` and re-add the bot if you want it to see everything.
- **`kind`** is `text`, or Telegram's own name for what arrived — `photo`,
  `voice`, `document`, `sticker`… The text is the caption, or `[photo]` when
  there is none. The file itself is not downloaded yet.

`receive` and `consume` start a listener if none is running. With a revoked or
mistyped token that listener is refused within a second, and they say so and
exit 3 rather than waiting for messages that cannot arrive. The poll offset
lives in memory on purpose: Telegram keeps unacknowledged updates for a day, so
a listener that was down for an hour catches up, and the inbox drops anything
it has already logged. A listener that was down for longer than a day misses
what arrived in between — Telegram no longer has it.

Two failures end the listener with exit 3 instead of retrying, because no
restart fixes them: the token was revoked (Telegram answers 401), or someone
else is reading this bot's updates (409 — another `co telegram listen` with the
same token, or a webhook set on the bot). Telegram hands each update to one
reader, so two listeners would each see a random half of the conversation.

`co telegram edit`, `delete` and `react` exist so the verbs match every other
provider, and say plainly that they are not wired up for Telegram yet.

To have your own agent answer, list the channel in `~/.co/host.yaml` under
`listen:` as `telegram` and run `co ai`, exactly as for Feishu.
