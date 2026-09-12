"""
Purpose: `co auth feishu` — scan once, and the app that receives your messages exists and is configured
LLM-Note:
  Dependencies: imports from [io, sys, qrcode, environment.py, env_file.py] and lazily from [lark_oapi] | imported by [cli/main.py via the auth command] | tested by [tests/unit/test_feishu_auth.py]
  Data flow: lark_oapi.register_app() → a verification link and a terminal QR → the person approves in Feishu → {client_id, client_secret, user_info.tenant_brand} → upsert_env writes FEISHU_APP_ID/SECRET (or LARK_*) to the selected env file
  State/Effects: creates a real Feishu application owned by the person who scans | writes two names to the selected env file | prints a link and a QR, never the secret
  Integration: the pair this writes is exactly what inbox/feishu.py reads, so `co feishu check` passes straight after | `co env set FEISHU_APP_SECRET` refuses and names this command, as the Google and Microsoft records do
  Performance: one HTTP round trip to begin, then a poll every few seconds until the person approves or ten minutes pass
  Errors: a missing SDK exits 3 with the pip command | a denied or expired scan is one line and exit 1 | a response without both halves writes nothing and exits 1

Why a scan and not a paste: Feishu has no API that hands out an app_secret —
`application/v6` never returns one, and reading it needs a token you can only
get if you already have the secret. The one documented way around that is the
platform's own scan-to-create-an-app flow, which registers an application in
the scanner's tenant and returns its credentials to whoever started the flow.
The request that begins it carries no client identity, so this is a public
protocol and not a private channel for the official CLI.

What one scan does not do: no API lists the applications you own, so the
choice of which application this becomes is made on Feishu's own confirmation
page. `--app-id` names one up front, which is how you reuse a bot that is
already in the group with its permissions set instead of creating one that is
in no group at all.

Where that id comes from, if `lark-cli` is installed: its `config.json` records
an app id per application in plain text. The *secret* beside it is a keychain
reference, and this never reads it. Copying a keychain entry into a plaintext
env file is a downgrade wearing the word "import" (#1497); scanning gets the
same credential with the platform's consent instead of the operating system's.
"""

import io
import re
import sys
from pathlib import Path
from typing import Optional

from ...environment import display_path, selected_env_file
from ...env_file import upsert_env

SDK_MISSING = "The Feishu SDK is not installed. Run: pip install lark-oapi"

# What the platform issues. Checked so a typo fails now rather than on a page.
_APP_ID = re.compile(r"^cli_[A-Za-z0-9]{8,}$")

# Shown on Feishu's confirmation page, so that a person looking at their list
# of applications a month from now knows what this one is and who made it.
APP_PRESET = {
    "name": "ConnectOnion",
    "desc": "Receives messages for a ConnectOnion agent and replies as this bot.",
}


def _register_app():
    """The SDK's registration flow, imported late so the CLI starts without it."""
    try:
        from lark_oapi import register_app
    except ImportError as exc:
        raise RuntimeError(SDK_MISSING) from exc
    return register_app


def lark_cli_applications() -> list:
    """Application ids `lark-cli` has configured, from its plaintext config.

    Ids only. `appSecret` there is `{"source": "keychain", "id": …}` and is
    left alone. A config that is missing, unreadable or not JSON yields
    nothing: this is a convenience, and a broken one must not stop a scan.
    """
    import json

    config = Path.home() / ".lark-cli" / "config.json"
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        apps = data.get("apps") or []
    except Exception:
        return []
    found = []
    for app in apps:
        if not isinstance(app, dict) or not app.get("appId"):
            continue
        users = app.get("users") or []
        user = users[0].get("userName") if users and isinstance(users[0], dict) else None
        found.append({"app_id": str(app["appId"]),
                      "brand": str(app.get("brand") or ""),
                      "user": user})
    return found


def _offer_existing() -> None:
    """Say that a reusable application is already configured, before creating one."""
    apps = lark_cli_applications()
    if not apps:
        return
    print(f"lark-cli has {len(apps)} application(s) configured on this machine:")
    for app in apps:
        who = f"  ({app['user']})" if app["user"] else ""
        print(f"  {app['app_id']}  {app['brand']}{who}")
    print("To authorize one of those instead of creating a new one, and keep the")
    print("groups and permissions it already has:")
    print(f"  co auth feishu --app-id {apps[0]['app_id']}")
    print()


def _qr(url: str) -> str:
    import qrcode

    code = qrcode.QRCode(border=1)
    code.add_data(url)
    out = io.StringIO()
    # invert=True draws dark modules as light blocks, which is what a phone
    # camera expects on the dark terminals most people use.
    code.print_ascii(out=out, invert=True)
    return out.getvalue()


def handle_feishu_auth(brand: str = "feishu", app_id: Optional[str] = None) -> None:
    """Create the application by scanning, or authorize one you already have."""
    if app_id is not None:
        # Checked before the scan: a typo here sends someone to a page that
        # cannot work, and they find out after waiting for a QR to expire.
        if not _APP_ID.match(app_id):
            print(f"{app_id!r} is not an application id. They look like cli_a1b2c3d4e5f6g7h8 "
                  "and are shown by `co auth feishu` when lark-cli has any configured.")
            raise SystemExit(2)
    try:
        register_app = _register_app()
    except RuntimeError as error:
        print(str(error))
        raise SystemExit(3)

    if app_id is None:
        _offer_existing()
        print("Creating a Feishu application. Scan this with the Feishu or Lark app,")
        print("or open the link, and approve it. The application is yours, in your tenant.")
    else:
        print(f"Authorizing {app_id}. Scan this with the Feishu or Lark app, or open")
        print("the link, and approve it. Its groups and permissions are unchanged.")
    print()

    def show(info) -> None:
        url = info.get("url", "")
        print(_qr(url))
        print(url)
        print()
        print("Waiting for approval. Ctrl-C to stop.")

    try:
        options = {"source": "connectonion"}
        if app_id is None:
            # A preset only pre-fills the creation page, so it is meaningless
            # — and confusing — when the application already exists and has a
            # name its owner chose.
            options["app_preset"] = dict(APP_PRESET)
        else:
            options["app_id"] = app_id
        result = register_app(on_qr_code=show, **options)
    except KeyboardInterrupt:
        print("Stopped. Nothing was saved.")
        raise SystemExit(1)
    except Exception as error:
        # The platform's own sentence, once. A traceback through the SDK says
        # nothing the sentence does not, and "denied" and "expired" are both
        # things a person did, not faults to debug.
        print(str(error) or type(error).__name__)
        raise SystemExit(1)

    app_id = (result or {}).get("client_id") or ""
    app_secret = (result or {}).get("client_secret") or ""
    if not (app_id and app_secret):
        # Half a credential is worse than none: it would be written, then fail
        # at connect time with an error about the half that is there.
        print("Feishu returned an incomplete registration; nothing was saved. Next: co auth feishu")
        raise SystemExit(1)

    # The flow always begins on Feishu and moves to Lark if that is where the
    # scanner's tenant lives, so which of the two this is, is known only now.
    tenant = ((result or {}).get("user_info") or {}).get("tenant_brand") or brand
    prefix = "LARK" if str(tenant).lower() == "lark" else "FEISHU"

    path = selected_env_file()
    upsert_env(path, {f"{prefix}_APP_ID": app_id, f"{prefix}_APP_SECRET": app_secret})
    print(f"✓ {prefix} application {app_id} saved to {display_path(path)}")
    print()
    print("Add the bot to a group and @ it, or send it a direct message.")
    print(f"Next: co {prefix.lower()} check")
