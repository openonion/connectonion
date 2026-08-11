"""
Purpose: Send a Telegram message from your own bot — the cheapest channel that can interrupt a human
LLM-Note:
  Dependencies: imports from [os, requests] | imported by [useful_tools/__init__.py, cli/commands/telegram_commands.py] | tested by [tests/unit/test_telegram.py]
  Data flow: send_telegram(chat, message) → reads TELEGRAM_BOT_TOKEN → POST api.telegram.org/bot<token>/sendMessage → returns {success, message_id, chat, error}
  State/Effects: one HTTP POST per message | no local state | no credential of ours is involved — the bot belongs to the user
  Integration: exposed as an agent tool and as `co telegram send` | the token comes from the user's own @BotFather bot, like Gmail's OAuth token rather than like a carrier account
  Errors: returns {success: False, error} for a missing token or a refused send — the caller decides whether that is fatal
"""

import os
from typing import Dict

import requests


API = "https://api.telegram.org"

NO_TOKEN = (
    "TELEGRAM_BOT_TOKEN is not set. Create a bot by messaging @BotFather on "
    "Telegram, then put the token it gives you in ~/.co/keys.env as "
    "TELEGRAM_BOT_TOKEN. The bot is yours — nothing is billed to it."
)


def send_telegram(chat: str, message: str) -> Dict:
    """Send a Telegram message from your bot.

    Args:
        chat: Who receives it — a numeric chat id, or @channelname for a channel
        message: The text to send

    Returns:
        dict: {success, message_id, chat, error}
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return {"success": False, "error": NO_TOKEN}

    response = requests.post(
        f"{API}/bot{token}/sendMessage",
        json={"chat_id": chat, "text": message},
        timeout=15,
    )
    body = response.json()

    if not body.get("ok"):
        # Telegram's own description is more useful than anything we would
        # write: "chat not found" and "bot was blocked by the user" are
        # different problems with different fixes.
        return {
            "success": False,
            "error": f"Telegram refused the message: {body.get('description', response.text[:200])}",
            "chat": chat,
        }

    return {
        "success": True,
        "message_id": body["result"]["message_id"],
        "chat": chat,
    }
