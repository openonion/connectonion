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

What one scan does not do: it cannot list the applications you already own —
no such API exists — so this always creates a new one rather than offering a
choice. Which application it becomes is decided on Feishu's own confirmation
page, which is the right place for that decision to be made.
"""

import io
import sys

from ...environment import display_path, selected_env_file
from ...env_file import upsert_env

SDK_MISSING = "The Feishu SDK is not installed. Run: pip install lark-oapi"

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


def _qr(url: str) -> str:
    import qrcode

    code = qrcode.QRCode(border=1)
    code.add_data(url)
    out = io.StringIO()
    # invert=True draws dark modules as light blocks, which is what a phone
    # camera expects on the dark terminals most people use.
    code.print_ascii(out=out, invert=True)
    return out.getvalue()


def handle_feishu_auth(brand: str = "feishu") -> None:
    """Create the application by scanning, and save what it needs to run."""
    try:
        register_app = _register_app()
    except RuntimeError as error:
        print(str(error))
        raise SystemExit(3)

    print("Creating a Feishu application. Scan this with the Feishu or Lark app,")
    print("or open the link, and approve it. The application is yours, in your tenant.")
    print()

    def show(info) -> None:
        url = info.get("url", "")
        print(_qr(url))
        print(url)
        print()
        print("Waiting for approval. Ctrl-C to stop.")

    try:
        result = register_app(
            on_qr_code=show,
            app_preset=dict(APP_PRESET),
            source="connectonion",
        )
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
