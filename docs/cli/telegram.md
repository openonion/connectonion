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
Inbound Telegram messages triggering an agent are a separate feature tracked
in issue #352.
