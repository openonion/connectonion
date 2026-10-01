"""
Purpose: `co auth slack` — create the Slack app from one manifest, paste its tokens, and have each one checked before it is saved
LLM-Note:
  Dependencies: imports from [getpass, json, os, sys, urllib.parse, environment.py, env_file.py, inbox/slack.py (APPS, scopes), cli/commands/slack_commands.py (SlackWeb)] | imported by [cli/main.py via the auth command] | tested by [tests/unit/test_slack_auth.py]
  Data flow: print the manifest link and the three clicks → tokens from hidden prompts (a terminal) or stdin (anything else, told apart by prefix) → auth.test for xoxb-/xoxp- (scopes from x-oauth-scopes), apps.connections.open for xapp- → upsert_env writes SLACK_BOT_TOKEN, SLACK_APP_TOKEN and, when given, SLACK_USER_TOKEN to the selected env file
  State/Effects: writes up to three names to the selected env file, only after every token given was accepted by Slack | creates nothing in Slack itself: the person creates the app from the manifest
  Integration: the names it writes are exactly what inbox/slack.py and slack_commands.py read, so `co slack check` passes straight after | a token is never an argument (shell history, ps), never printed
  Errors: a token Slack rejects exits 1 with Slack's code and nothing saved | a missing required token exits 1 naming it | missing scopes are listed with the reinstall step, and the tokens are still saved (they work; the scopes are one click away)

Why a manifest and a paste: Slack has no flow that hands a CLI a bot token
without a redirect URL to receive it, and a local OAuth server would need the
app's client secret first. A manifest is the documented way to create an app
already configured — Socket Mode on, events subscribed, every scope listed — so
the seven manual steps become: open a link, pick the workspace, Next, Create, Install, and
make one app-level token (manifests cannot create that one).
"""

import getpass
import json
import sys
from urllib.parse import quote

from ...env_file import upsert_env
from ...environment import display_path, selected_env_file, setting
from ...inbox.slack import APPS, INBOX_SCOPES, READ_SCOPES, SEARCH_SCOPES
from .command_tips import print_tip
from .slack_commands import SlackWeb

BOT_SCOPES = sorted(set(INBOX_SCOPES) | set(READ_SCOPES))

MANIFEST = {
    "display_information": {"name": "ConnectOnion",
                            "description": "Reads and answers Slack for a ConnectOnion agent."},
    "features": {
        "app_home": {"home_tab_enabled": False, "messages_tab_enabled": True,
                     "messages_tab_read_only_enabled": False},
        "bot_user": {"display_name": "ConnectOnion", "always_online": True},
    },
    "oauth_config": {"scopes": {"bot": BOT_SCOPES, "user": list(SEARCH_SCOPES)}},
    "settings": {
        "event_subscriptions": {"bot_events": ["app_mention", "message.channels", "message.im"]},
        "interactivity": {"is_enabled": False},
        "org_deploy_enabled": False,
        "socket_mode_enabled": True,
        "token_rotation_enabled": False,
    },
}

# (env name, prefix, what Slack calls it, where it is, required)
TOKENS = (
    ("SLACK_BOT_TOKEN", "xoxb-", "Bot User OAuth Token", "Install App", True),
    ("SLACK_USER_TOKEN", "xoxp-", "User OAuth Token, optional, for search", "Install App", False),
    ("SLACK_APP_TOKEN", "xapp-", "app-level token", "Basic Information → App-Level Tokens", True),
)


def manifest_link() -> str:
    return f"{APPS}?new_app=1&manifest_json={quote(json.dumps(MANIFEST, separators=(',', ':')))}"


def print_steps() -> None:
    print("Slack setup: one app of your own, made from a manifest.\n")
    print("1. Open this link. Slack shows Create from a manifest, already filled in; pick your")
    print("   workspace, click Next, then Create (its 3rd-party and Socket Mode notes are expected):")
    print(f"   {manifest_link()}")
    print("   (If the form is empty: Create New App → From a manifest → JSON, and paste:)")
    print(f"   {json.dumps(MANIFEST, separators=(',', ':'))}")
    print("2. Install App → Install to Workspace → Allow. Copy the Bot User OAuth Token (xoxb-…)")
    print("   and, for co slack search, the User OAuth Token (xoxp-…).")
    print("3. Basic Information → App-Level Tokens → Generate Token and Scopes: add connections:write,")
    print("   Generate, and copy the token (xapp-…).\n")


def read_tokens() -> dict:
    """{env name: token} for the tokens pasted. A terminal gets one hidden prompt per
    token, and Enter keeps what is set; anything else is read whole from stdin and
    sorted by prefix."""
    if not sys.stdin.isatty():
        words = sys.stdin.read().split()
        given = {name: next((w for w in words if w.startswith(prefix)), "")
                 for name, prefix, *_ in TOKENS}
    else:
        given = {name: _ask(name, prefix, label, where) for name, prefix, label, where, _ in TOKENS}
    for name, prefix, label, where, required in TOKENS:
        if required and not (given[name] or setting(name)):
            print(f"No {label} ({prefix}…, from {where}); nothing was saved. Next: co auth slack",
                  file=sys.stderr)
            sys.exit(1)
    return {name: token for name, token in given.items() if token}


def _ask(name: str, prefix: str, label: str, where: str) -> str:
    keep = " (Enter keeps the one set now)" if setting(name) else ""
    while True:
        token = getpass.getpass(f"{label} ({prefix}…, from {where}){keep}: ").strip()
        if not token or token.startswith(prefix):
            return token
        print(f"That does not start with {prefix}. Paste the {label}, or press Enter.")


def verify_bot(token: str) -> tuple:
    """(the bot's name, the bot scopes it lacks)."""
    response = SlackWeb(token, "SLACK_BOT_TOKEN").post("auth.test")
    result = response.json()
    if not result.get("ok"):
        _rejected("SLACK_BOT_TOKEN", result)
    name = result.get("user") or "your bot"
    print(f"✓ bot {name} in {result.get('team', '?')} ({result.get('url', '')})")
    return name, _lacking(response, BOT_SCOPES)


def verify_app(token: str) -> None:
    result = SlackWeb(token, "SLACK_APP_TOKEN").post("apps.connections.open").json()
    if not result.get("ok"):
        _rejected("SLACK_APP_TOKEN", result)
    print("✓ app-level token opens Socket Mode")


def verify_user(token: str) -> list:
    """The user scopes co slack search needs that this token lacks."""
    response = SlackWeb(token, "SLACK_USER_TOKEN").post("auth.test")
    result = response.json()
    if not result.get("ok"):
        _rejected("SLACK_USER_TOKEN", result)
    print(f"✓ user token for {result.get('user', '?')} (co slack search)")
    return _lacking(response, SEARCH_SCOPES)


def _lacking(response, wanted) -> list:
    granted = {scope.strip() for scope in response.headers.get("x-oauth-scopes", "").split(",")}
    return [scope for scope in wanted if scope not in granted]


def _rejected(name: str, result: dict) -> None:
    error = result.get("error") or "unknown_error"
    hint = " It needs the scope connections:write." if name == "SLACK_APP_TOKEN" and error == "missing_scope" else ""
    print(f"Slack rejected {name} ({error}).{hint} Nothing was saved. Next: co auth slack", file=sys.stderr)
    sys.exit(1)


def handle_slack_auth() -> None:
    print_steps()
    given = read_tokens()
    # What is checked is what the commands will read: pasted, else already set.
    tokens = {name: given.get(name) or setting(name) or "" for name, *_ in TOKENS}
    bot, scopes = verify_bot(tokens["SLACK_BOT_TOKEN"])
    lacking = [("Bot Token Scopes", scopes)]
    verify_app(tokens["SLACK_APP_TOKEN"])
    if tokens["SLACK_USER_TOKEN"]:
        lacking.append(("User Token Scopes", verify_user(tokens["SLACK_USER_TOKEN"])))
    if given:
        path = selected_env_file()
        upsert_env(path, given)
        print(f"✓ saved {', '.join(given)} to {display_path(path)}")
    for where, scopes in lacking:
        if scopes:
            print(f"Missing {where}: {', '.join(scopes)}. At {APPS} open your app → OAuth & Permissions → "
                  f"{where}, add them, then Reinstall to Workspace.")
    print(f"Invite the bot to each channel it should read: /invite @{bot} in that channel.")
    print_tip("Next: co slack check")
