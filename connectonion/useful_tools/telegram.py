"""
Purpose: Send a Telegram message from your own bot — the cheapest channel that can interrupt a human
LLM-Note:
  Dependencies: imports from [os, requests] | imported by [useful_tools/__init__.py, cli/commands/telegram_commands.py] | tested by [tests/unit/test_telegram.py]
  Data flow: send_telegram(chat, message) → reads TELEGRAM_BOT_TOKEN → POST api.telegram.org/bot<token>/sendMessage → returns {success, message_id, chat, error}
  State/Effects: one HTTP POST per message | no local state | no credential of ours is involved — the bot belongs to the user
  Integration: exposed as an agent tool and as `co telegram send` | the token comes from the user's own @BotFather bot, like Gmail's OAuth token rather than like a carrier account
  Errors: returns {success: False, error, chat} for setup, transport, protocol, and Telegram refusals without exposing the token-bearing URL
"""

import os

import requests


API = "https://api.telegram.org"

NO_TOKEN = (
    "TELEGRAM_BOT_TOKEN is not set. Create a bot by messaging @BotFather on "
    "Telegram, then put the token it gives you in ~/.co/keys.env as "
    "TELEGRAM_BOT_TOKEN. The bot is yours — nothing is billed to it."
)


def _failure(chat: str, error: str) -> dict[str, object]:
    return {"success": False, "error": error, "chat": chat}


def _result_from_response(response, *, token: str, chat: str) -> dict[str, object]:
    """Translate Telegram's envelope without echoing raw responses or URLs."""
    status = getattr(response, "status_code", "unknown")
    try:
        body = response.json()
    except ValueError:
        return _failure(chat, f"Telegram returned HTTP {status} without JSON.")

    if not isinstance(body, dict):
        return _failure(chat, "Telegram returned an invalid response.")
    if not body.get("ok"):
        description = body.get("description")
        if isinstance(description, str) and description:
            safe_description = description.replace(token, "[redacted]")[:500]
            return _failure(chat, f"Telegram refused the message: {safe_description}")
        return _failure(chat, f"Telegram refused the message (HTTP {status}).")

    result = body.get("result")
    message_id = result.get("message_id") if isinstance(result, dict) else None
    if message_id is None:
        return _failure(chat, "Telegram returned an invalid success response.")
    return {"success": True, "message_id": message_id, "chat": chat}


def send_telegram(chat: str, message: str) -> dict[str, object]:
    """Send a Telegram message from your bot.

    Args:
        chat: Who receives it — a numeric chat id, or @channelname for a channel
        message: The text to send

    Returns:
        dict: {success, message_id, chat, error}
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return _failure(chat, NO_TOKEN)

    try:
        response = requests.post(
            f"{API}/bot{token}/sendMessage",
            json={"chat_id": chat, "text": message},
            timeout=15,
        )
    except requests.RequestException as exc:
        # Request exception strings can contain the URL, and Telegram puts the
        # bot token in that URL. The class names the failure without the secret.
        return _failure(chat, f"Telegram request failed ({type(exc).__name__}).")
    return _result_from_response(response, token=token, chat=chat)
