"""
Purpose: `co discord link` — link the owner's own Discord account (experimental), by QR or a pasted token
LLM-Note:
  Dependencies: imports from [asyncio, getpass, sys, httpx, rich, inbox/discord_user.py, inbox/discord_remote_auth.py, cli/commands/feishu_auth.py (_qr), cli/commands/listen_commands.py (errors)] | imported by [cli/main.py] | tested by [tests/unit/test_inbox_discord_user.py]
  Data flow: warning → --yes or an interactive confirm → QR (remote auth) or hidden paste → GET /users/@me → save_session() → the account name and the next command
  State/Effects: writes ~/.co/inbox/discord/user-session.json (0600) and removes user-stopped.json; prints the QR only to this terminal
  Integration: after linking, every other `co discord` verb acts as this account (inbox/discord_user.py account())
  Errors: exit 2 without --yes when there is no terminal to ask | exit 1 when Discord refuses, asks for a captcha (says to paste instead), or the phone cancels
"""

import asyncio
import getpass
import sys

import httpx

from ...inbox.discord_remote_auth import exchange, new_key, ticket
from ...inbox.discord_user import API, save_session, web_headers
from ...inbox.store import Inbox
from .command_tips import print_tip
from .listen_commands import errors

WARNING = (
    "Linking makes ConnectOnion act as your own Discord account (a \"self-bot\"). Discord's terms "
    "forbid automating a user account (https://support.discord.com/hc/articles/115002192352), and "
    "Discord can limit or terminate the account for it. Try it on a throwaway account first. "
    "It only reads and answers existing DMs and group DMs (plus channels you allowlist), never "
    "opens a new DM, sends a friend request or joins a server, and stops for good the first time "
    "Discord objects."
)


def _http() -> httpx.Client:
    return httpx.Client(timeout=15)


def handle_link(yes: bool = False, token: bool = False) -> None:
    """Link the account and say who it is."""
    errors.print(WARNING, style="yellow")
    _accepted_or_exit(yes)
    http = _http()
    value = _pasted() if token else _scanned(http)
    user = _verified(http, value)
    box = Inbox("discord")
    path = save_session(box, value, user, "paste" if token else "qr")
    print(f"linked @{user.get('username')} · {path}")
    print("Use this session for co only: a token shared with another client is what gets accounts flagged.")
    running = box.listener_pid() is not None
    print_tip("Next: co discord listen --restart" if running else "Next: co discord listen")


def _accepted_or_exit(yes: bool) -> None:
    if yes:
        return
    if not sys.stdin.isatty():
        errors.print("not linked: pass --yes to accept the warning above", style="red")
        sys.exit(2)
    if input("Link this account anyway? [y/N] ").strip().lower() not in ("y", "yes"):
        errors.print("not linked", style="red")
        sys.exit(1)


def _pasted() -> str:
    value = getpass.getpass("Discord token (hidden): ") if sys.stdin.isatty() else sys.stdin.read()
    if not value.strip():
        errors.print("not linked: no token was given", style="red")
        sys.exit(2)
    return value.strip()


def _scanned(http) -> str:
    from .feishu_auth import _qr

    def show_qr(url: str) -> None:
        print(_qr(url))
        print("Scan this with the Discord phone app (You → the QR icon → Scan). It works once and "
              "expires in about two minutes. Never show it to anyone: it hands over the account.")

    def show_user(user: dict) -> None:
        print(f"The phone is logging in as @{user['username']}. Confirm on the phone only if that "
              "is the account to link.")

    key = new_key()
    try:
        login = asyncio.run(ticket(show_qr, show_user, key=key))
        return exchange(http, key, login)
    except RuntimeError as exc:  # a captcha, a cancel on the phone, an expired QR: each says what next
        errors.print(str(exc), style="red")
        sys.exit(1)


def _verified(http, token: str) -> dict:
    response = http.get(f"{API}/users/@me", headers=web_headers(token))
    if response.status_code != 200:
        errors.print(f"Discord did not accept that token (HTTP {response.status_code}); nothing was linked. "
                     "Next: co discord link --yes", style="red")
        sys.exit(1)
    return response.json()
