"""A missing bot scope is one click away, not a trip to the Developer Console.

`co lark listen` recovers a connection gap by reading group history, which needs
the bot scope `im:message.group_msg`. An application created by `co auth` did not
have it, and neither did one set up by hand from our own instructions (#1544), so
recovery could never run for anyone.

`lark-cli` solves this without a console visit. From
`cmd/event/console_url.go` (MIT, larksuite/cli):

    {open-host}/page/launcher?clientID=<appID>&addons=<base64url(gzip(json))>

and its own comment on what that link does: "The bot-specific scan-to-enable link
adds the scopes to the app manifest, after which the tenant token carries them."

Verified on a real tenant on 2026-09-15: the page listed "Act as app / Read all
messages in associated group chat (sensitive scope)", and after Confirm the bot's
tenant token read group history that had refused it minutes earlier with
`230027 … need scope: im:message.group_msg`.

Three details are load-bearing and each has a test below, because getting any one
wrong produces a page that looks fine and grants nothing — which is how the first
attempt failed:

  * the path is `/page/launcher`, not the `/page/cli` the registration flow uses
  * the parameter is `clientID` (camelCase), carrying the app's own id
  * `tenant` and `user` are both present as arrays; the spec reads a missing side
    as empty, and omitting one is how the first attempt silently granted nothing
"""

import base64
import gzip
import json
from urllib.parse import parse_qs, urlparse

import pytest

from connectonion.cli.commands import feishu_auth


def decoded(url):
    raw = parse_qs(urlparse(url).query)["addons"][0]
    padded = raw + "=" * (-len(raw) % 4)
    return json.loads(gzip.decompress(base64.urlsafe_b64decode(padded)))


def test_the_link_lands_on_the_launcher_not_the_cli_page():
    """`/page/cli` serves registration; the manifest update is `/page/launcher`."""
    url = feishu_auth.scan_to_enable_url("lark", "cli_abc123def456", tenant=["im:message.group_msg"])

    assert urlparse(url).path == "/page/launcher"
    assert "/page/cli" not in url


def test_it_carries_the_apps_own_id_as_clientID():
    url = feishu_auth.scan_to_enable_url("lark", "cli_abc123def456", tenant=["im:message.group_msg"])

    assert parse_qs(urlparse(url).query)["clientID"] == ["cli_abc123def456"]
    assert "user_code" not in url, "this link is not part of the registration flow"


def test_both_scope_sides_are_present_even_when_empty():
    """Omitting a side is how the first attempt granted nothing while saying 'App updated'."""
    payload = decoded(feishu_auth.scan_to_enable_url("lark", "cli_x1y2z3a4b5", tenant=["im:message.group_msg"]))

    assert payload["scopes"]["tenant"] == ["im:message.group_msg"]
    assert payload["scopes"]["user"] == [], "must be an empty array, not absent"


def test_a_user_scope_goes_to_the_user_side():
    payload = decoded(feishu_auth.scan_to_enable_url("lark", "cli_x1y2z3a4b5", user=["im:message.group_msg:get_as_user"]))

    assert payload["scopes"]["user"] == ["im:message.group_msg:get_as_user"]
    assert payload["scopes"]["tenant"] == []


def test_the_brand_picks_the_host():
    lark = feishu_auth.scan_to_enable_url("lark", "cli_x1y2z3a4b5", tenant=["a"])
    feishu = feishu_auth.scan_to_enable_url("feishu", "cli_x1y2z3a4b5", tenant=["a"])

    assert urlparse(lark).netloc == "open.larksuite.com"
    assert urlparse(feishu).netloc == "open.feishu.cn"


def test_the_encoding_round_trips_through_the_front_ends_chain():
    """JSON -> gzip -> base64url without padding, which is what the page decodes."""
    url = feishu_auth.scan_to_enable_url("lark", "cli_x1y2z3a4b5", tenant=["im:message.group_msg"],
                                         events=["im.message.receive_v1"])
    payload = decoded(url)

    assert payload["events"]["items"]["tenant"] == ["im.message.receive_v1"]
    assert payload["events"]["items"]["user"] == []
    assert "=" not in parse_qs(urlparse(url).query)["addons"][0], "base64url carries no padding"


def test_nothing_to_grant_is_refused_rather_than_linked():
    """A link that grants nothing wastes a click and teaches the reader nothing."""
    with pytest.raises(ValueError):
        feishu_auth.scan_to_enable_url("lark", "cli_x1y2z3a4b5")


def test_the_registration_addons_declare_both_sides_too():
    """The same spec applies where `co auth` asks for scopes at creation time."""
    assert feishu_auth.APP_ADDONS["scopes"]["user"] == []
    assert "im:message.group_msg" in feishu_auth.APP_ADDONS["scopes"]["tenant"]
    assert feishu_auth.APP_ADDONS["events"]["items"]["user"] == []
