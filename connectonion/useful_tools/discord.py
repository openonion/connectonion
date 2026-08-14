"""
Purpose: Post a Discord message — as your bot to a channel, or through a webhook URL
LLM-Note:
  Dependencies: imports from [os, requests] | imported by [useful_tools/__init__.py, cli/commands/discord_commands.py] | tested by [tests/unit/test_discord.py]
  Data flow: send_discord(channel, message) → webhook URL posts straight to it | channel id reads DISCORD_BOT_TOKEN → POST discord.com/api/v10/channels/<id>/messages → returns {success, message_id, channel, error}
  State/Effects: one HTTP POST per message | no local state | no credential of ours is involved — the bot is the user's own
  Integration: exposed as an agent tool and as `co discord send` | the token is from the user's own Discord application, like Telegram's bot token rather than a carrier account
  Errors: returns {success: False, error, channel} for setup, transport and Discord refusals, without echoing the token or a webhook URL
"""

import os

import requests


API = "https://discord.com/api/v10"

# Discord caps a message at 2000 characters and rejects the whole thing above
# it, so a long release note fails at the API rather than being truncated.
MAX_MESSAGE = 2000

NO_TOKEN = (
    "DISCORD_BOT_TOKEN is not set, and the target is not a webhook URL. Either "
    "pass a webhook URL, or create a bot at "
    "https://discord.com/developers/applications and put its token in "
    "~/.co/keys.env as DISCORD_BOT_TOKEN. The bot is yours — nothing is billed to it."
)


def send_discord(channel: str, message: str) -> dict[str, object]:
    """Post a message to Discord.

    Args:
        channel: A channel id (posts as your bot), or a webhook URL (posts as
            the webhook). Webhooks need no bot and no token.
        message: The text to post. Discord's limit is 2000 characters.

    Returns:
        dict: {success, message_id, channel, error}
    """
    if not message:
        return _failure(channel, "Discord rejects an empty message.")
    if len(message) > MAX_MESSAGE:
        return _failure(
            channel,
            f"Discord rejects messages over {MAX_MESSAGE} characters; this one is "
            f"{len(message)}. Split it rather than letting the API refuse the whole post.",
        )

    if channel.startswith("https://"):
        return _post(channel, {"content": message}, headers={}, channel=channel)

    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        return _failure(channel, NO_TOKEN)

    return _post(
        f"{API}/channels/{channel}/messages",
        {"content": message},
        headers={"Authorization": f"Bot {token}"},
        channel=channel,
        token=token,
    )


def _post(url, payload, *, headers, channel, token=None) -> dict[str, object]:
    """One POST, with the message carried as JSON.

    `json=` is the whole point of this function. The release path hand-built
    the body with `curl -d "{...}"`, and a backtick or a backslash in a release
    note broke the quoting and came back as Discord error 50109, invalid JSON.
    Serialising in the library cannot make that mistake.
    """
    try:
        response = requests.post(
            url, json=payload, headers={**headers, "User-Agent": "connectonion"}, timeout=15
        )
    except requests.RequestException as exc:
        # A webhook URL is itself a secret, and it appears in the exception's
        # string form. The class names the failure without leaking it.
        return _failure(channel, f"Discord request failed ({type(exc).__name__}).")

    return _read(response, channel=channel, token=token)


def _read(response, *, channel, token) -> dict[str, object]:
    """Discord's own reason, kept — 50109 and "unknown channel" need different fixes."""
    if response.status_code in (200, 204):
        return {"success": True, "message_id": _message_id(response), "channel": channel}

    try:
        body = response.json()
    except ValueError:
        return _failure(channel, f"Discord returned HTTP {response.status_code} without JSON.")

    reason = body.get("message") if isinstance(body, dict) else None
    code = body.get("code") if isinstance(body, dict) else None
    detail = f"{reason} (code {code})" if reason and code else (reason or str(body)[:200])
    if token:
        detail = detail.replace(token, "[redacted]")
    return _failure(channel, f"Discord refused the message: {detail}")


def _message_id(response):
    """Webhooks answer 204 with no body; a bot post answers 200 with the message."""
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("id") if isinstance(body, dict) else None


def _failure(channel: str, error: str) -> dict[str, object]:
    return {"success": False, "error": error, "channel": _safe(channel)}


def _safe(channel: str) -> str:
    """A webhook URL carries its own token, so it never goes back in a result."""
    return "webhook" if channel.startswith("https://") else channel
