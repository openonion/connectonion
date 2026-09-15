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
import json
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ...environment import display_path, selected_env_file
from ...env_file import upsert_env
from .command_tips import print_tip

SDK_MISSING = "The Feishu SDK is not installed. Run: pip install lark-oapi"

# What the platform issues. Checked so a typo fails now rather than on a page.
_APP_ID = re.compile(r"^cli_[A-Za-z0-9]{8,}$")

# Shown on Feishu's confirmation page, so that a person looking at their list
# of applications a month from now knows what this one is and who made it.
APP_PRESET = {
    "name": "ConnectOnion",
    "desc": "Receives messages for a ConnectOnion agent and replies as this bot.",
}

# What the application has to be allowed to do, declared at the moment someone
# approves it — so one scan produces a bot that works, rather than a bot that
# receives messages and then fails at the first thing it tries.
#
# Until this was added, `co auth` created an application with no scopes of its
# own. Receiving and replying happened to work; history recovery did not, and
# could not for anyone, by either the automatic or the documented manual route
# (#1544). Measured 2026-09-15: the bot's own token was refused with
# `230027 … need scope: im:message.group_msg`, which is the call
# inbox/recovery.py makes after a connection gap.
#
# These are *tenant* scopes on purpose. The bot acts as itself, not on a
# person's behalf: `im/v1/messages` is called with a tenant token, and the
# user-delegated grant from `lark-cli auth login` does not satisfy it — checked,
# after that route reported "no permissions to add or authorize here" while the
# tenant call kept failing.
# Both sides of every section are always present, even when empty. The spec reads
# a missing `tenant` or `user` as an empty array, and lark-cli is explicit about
# keeping them non-nil for exactly that reason — the first version of this omitted
# `user`, and the page answered "App updated" while granting nothing.
APP_ADDONS = {
    "scopes": {
        "tenant": [
            "im:message.group_at_msg:readonly",  # group messages that @ the bot
            "im:message.p2p_msg:readonly",       # direct messages
            "im:message:send_as_bot",            # reply
            "im:message.group_msg",              # read group history, for recovery
        ],
        "user": [],
    },
    "events": {"items": {"tenant": ["im.message.receive_v1"], "user": []}},
}

# The scan-to-enable deep link: one URL that adds scopes to an existing
# application's manifest, with no Developer Console visit.
#
# From lark-cli, `cmd/event/console_url.go` (MIT, larksuite/cli), whose own
# comment is the contract: "The bot-specific scan-to-enable link adds the scopes
# to the app manifest, after which the tenant token carries them."
#
#     {open-host}/page/launcher?clientID=<appID>&addons=<base64url(gzip(json))>
#
# Three details are load-bearing, and getting any of them wrong produces a page
# that looks right and grants nothing — measured, on all three:
#   * `/page/launcher`, not the `/page/cli` the registration flow uses
#   * `clientID`, camelCase, carrying the app's own id — and no user_code, because
#     this is not part of registration
#   * both scope sides present as arrays
_ADDONS_PATH = "/page/launcher"


def _encode_addons(payload: dict) -> str:
    """JSON → gzip → base64url without padding, the chain the page decodes."""
    import base64
    import gzip

    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(gzip.compress(raw, mtime=0)).decode("ascii").rstrip("=")


def scan_to_enable_url(brand: str, app_id: str, *, tenant=(), user=(), events=()) -> str:
    """A link that, once approved, leaves `app_id` holding these scopes.

    Raises rather than returning a link that would grant nothing: an empty one
    still renders a confirmation page, so the reader clicks, sees success, and
    learns nothing about why their command still fails.
    """
    tenant, user, events = list(tenant), list(user), list(events)
    if not (tenant or user or events):
        raise ValueError("scan_to_enable_url needs at least one scope or event to ask for")

    payload = {"scopes": {"tenant": tenant, "user": user}}
    if events:
        payload["events"] = {"items": {"tenant": events, "user": []}}
    host = OPEN_HOSTS.get(brand, OPEN_HOSTS["feishu"])
    return f"{host}{_ADDONS_PATH}?clientID={app_id}&addons={_encode_addons(payload)}"

# Where a person actually approves.
#
# The SDK hands us the server's `verification_uri_complete`, which is
# `<open-host>/page/launcher?user_code=…`. That page is the wrong one: it reads
# the code, deletes it from the address bar, calls its own ack endpoint, and on
# any failure renders **"Link expired"** — for a code the registration endpoint
# reports as `authorization_pending` in the same second. Measured twice, on
# 2026-09-14 and again on 2026-09-15.
#
# `lark-cli` never sees that problem because it never uses that URL. It ignores
# `verification_uri_complete` and builds its own (MIT, larksuite/cli,
# internal/auth/app_registration.go):
#
#     verificationUriComplete := fmt.Sprintf("%s/page/cli?user_code=%s", ep.Open, userCode)
#
# `/page/cli` is the page that serves this flow. Pointed there, the same code
# that had just rendered "Link expired" produced the creation form, an
# application, and its secret — verified end to end on the same tenant.
#
# So the difference was never the tenant, the region, or the code's lifetime.
# It was one path segment.
OPEN_HOSTS = {
    "lark": "https://open.larksuite.com",
    "feishu": "https://open.feishu.cn",
}
CLI_PAGE = "/page/cli"

# lark-cli sends these three, and the launcher bundle reads `from` to pick its
# copy ("Re-run the CLI command" rather than a generic expiry). Ours says
# connectonion so the platform's own analytics do not attribute our traffic to
# their CLI.
CLI_QUERY_MARKS = {"from": "cli", "lpv": "connectonion", "ocv": "connectonion"}


def cli_page_url(url: str, brand: str) -> str:
    """The SDK's launcher link, pointed at the page that serves this flow.

    Host and path are replaced; the query is kept. The query is not decoration —
    it carries `user_code`, and the app preset that pre-fills the creation form's
    name and description. Rebuilding the URL from scratch, the way lark-cli does,
    would drop the preset, so this rewrites instead of reconstructing.

    An unparseable or empty URL is returned untouched: printing a link that at
    least matches what the SDK is polling for beats printing nothing.
    """
    if not url:
        return url
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    if not parsed.scheme or not parsed.netloc:
        return url

    host = OPEN_HOSTS.get(brand, OPEN_HOSTS["feishu"])
    target = urlparse(host)

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(CLI_QUERY_MARKS)

    return urlunparse((
        target.scheme,
        target.netloc,
        CLI_PAGE,
        parsed.params,
        urlencode(query),
        parsed.fragment,
    ))


def _link_life(expire_in) -> str:
    """State the TTL the server actually gave, never a guess.

    The SDK falls back to 600 when the response omits expires_in, and quoting
    that fallback as though it were measured is how "it expired after two
    minutes" got investigated as a timeout for an hour. If the number is not
    known, say that rather than inventing one.
    """
    try:
        seconds = int(expire_in)
    except (TypeError, ValueError):
        return "The platform did not say how long this link is valid."
    if seconds >= 120:
        return f"This link is valid for {seconds // 60} minutes ({seconds}s)."
    return f"This link is valid for {seconds}s."


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


def _offer_existing(brand: str = "feishu") -> None:
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
    # The application's own brand decides the verb. lark-cli recorded it when
    # the person logged in there, which is better evidence than what they
    # typed here — `co auth feishu` on a machine that only knows Lark apps
    # should still print a command that works.
    verb = apps[0]["brand"].lower() if apps[0]["brand"].lower() in ("lark", "feishu") else brand
    print(f"  co auth {verb} --app-id {apps[0]['app_id']}")
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
            # Naming the command to run, not only the shape of the thing that
            # was wrong: the caller is here because they do not have a valid id
            # to hand, and `co auth <brand>` with no --app-id both lists the ids
            # lark-cli knows and creates one when there are none.
            product = "lark" if brand == "lark" else "feishu"
            print(f"{app_id!r} is not an application id. They look like cli_a1b2c3d4e5f6g7h8.")
            print_tip(f"Next: co auth {product}")
            raise SystemExit(2)
    try:
        register_app = _register_app()
    except RuntimeError as error:
        print(str(error))
        raise SystemExit(3)

    if app_id is None:
        _offer_existing(brand)
        product = "Lark" if brand == "lark" else "Feishu"
        print(f"Creating a {product} application. Scan this with the Feishu or Lark app,")
        print("or open the link, and approve it. The application is yours, in your tenant.")
    else:
        print(f"Authorizing {app_id}. Scan this with the Feishu or Lark app, or open")
        print("the link, and approve it. Its groups and permissions are unchanged.")
    print()

    def show(info) -> None:
        url = cli_page_url(info.get("url", ""), brand)
        print(_qr(url))
        print(url)
        print()
        print(_link_life(info.get("expire_in")))
        print()
        print("Waiting for approval. Ctrl-C to stop.")

    try:
        options = {"source": "connectonion"}
        # No `domain` override. The registration protocol bootstraps on the
        # Feishu accounts host whichever brand you asked for, and lark-cli
        # leaves it there on purpose — `registrationBootstrapBrand =
        # core.BrandFeishu` — because brand selects the *verification host*, not
        # where the protocol begins. Polling moves to the scanner's tenant by
        # itself. This is the path verified end to end on a Lark tenant on
        # 2026-09-15: begin on accounts.feishu.cn, approve on
        # open.larksuite.com/page/cli, credentials returned by the poll.
        #
        # 1.8.5b8 set this to the Lark accounts host so a Lark user would not be
        # handed an open.feishu.cn link. That aim is right and is now met by
        # cli_page_url(), which decides the host the person actually sees.
        # Asked for on both paths, unlike the preset. A new application needs
        # them to work at all; an existing one reached with --app-id is shown
        # them on the same confirmation page as "your app will be updated with
        # these settings", which is how someone whose bot predates this adds
        # what it is missing — without a trip to the Developer Console.
        options["addons"] = dict(APP_ADDONS)
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
        product = "Lark" if brand == "lark" else "Feishu"
        print(
            f"{product} returned an incomplete registration; nothing was saved. "
            f"Next: co auth {brand}"
        )
        raise SystemExit(1)

    # `co auth lark` begins on Lark and `co auth feishu` on Feishu, but either
    # flow switches to the other when the scanner's tenant turns out to live
    # there — so which of the two this actually is, is known only now.
    tenant = ((result or {}).get("user_info") or {}).get("tenant_brand") or brand
    prefix = "LARK" if str(tenant).lower() == "lark" else "FEISHU"

    path = selected_env_file()
    upsert_env(path, {f"{prefix}_APP_ID": app_id, f"{prefix}_APP_SECRET": app_secret})
    print(f"✓ {prefix} application {app_id} saved to {display_path(path)}")
    print()
    print("Add the bot to a group and @ it, or send it a direct message.")
    print(f"Next: co {prefix.lower()} check")
