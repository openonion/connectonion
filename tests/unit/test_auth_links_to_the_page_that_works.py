"""The approval link points at /page/cli, the page that serves this flow.

The SDK hands us the server's `verification_uri_complete`, which is
`<open-host>/page/launcher?user_code=…`. That page reads the code, deletes it
from the address bar, calls its own ack endpoint, and renders **"Link expired"**
on any failure — for a code the registration endpoint reports as
`authorization_pending` in the same second.

`lark-cli` never hits that, because it never uses that URL. It builds its own
(MIT, larksuite/cli, internal/auth/app_registration.go):

    verificationUriComplete := fmt.Sprintf("%s/page/cli?user_code=%s", ep.Open, userCode)

Verified on the owner's Lark tenant on 2026-09-15: the same live code rendered
"Link expired" on /page/launcher and the working creation form on /page/cli,
which produced an application and its secret.

What these tests hold in place:

  * the printed link is /page/cli, never /page/launcher
  * it is on the host matching the brand the person asked for
  * `user_code` survives the rewrite — without it the link is inert
  * the app preset survives it too, or the creation form loses its prefill
  * nothing claims a live code has expired
"""

from urllib.parse import parse_qs, urlparse

import pytest

from connectonion.cli.commands import feishu_auth

LAUNCHER_LARK = (
    "https://open.larksuite.com/page/launcher"
    "?user_code=2W9P-M45A&name=ConnectOnion&desc=Receives+messages"
)
LAUNCHER_FEISHU = (
    "https://open.feishu.cn/page/launcher"
    "?user_code=JFWX-J2Y5&name=ConnectOnion&desc=Receives+messages"
)


def parts(url):
    p = urlparse(url)
    return p.scheme, p.netloc, p.path, parse_qs(p.query)


def test_the_link_is_not_the_launcher():
    """The one path segment that decided whether any of this worked."""
    url = feishu_auth.cli_page_url(LAUNCHER_LARK, "lark")

    assert "/page/launcher" not in url
    assert urlparse(url).path == "/page/cli"


def test_a_lark_user_gets_a_lark_host():
    _, netloc, path, _ = parts(feishu_auth.cli_page_url(LAUNCHER_LARK, "lark"))

    assert netloc == "open.larksuite.com"
    assert path == "/page/cli"


def test_a_feishu_user_gets_a_feishu_host():
    _, netloc, path, _ = parts(feishu_auth.cli_page_url(LAUNCHER_FEISHU, "feishu"))

    assert netloc == "open.feishu.cn"
    assert path == "/page/cli"


def test_the_brand_decides_the_host_not_the_url_handed_in():
    """The SDK bootstraps on Feishu whichever brand was asked for.

    So a Lark user's link arrives pointing at open.feishu.cn, and the rewrite is
    the only thing that puts them on their own product.
    """
    _, netloc, _, query = parts(feishu_auth.cli_page_url(LAUNCHER_FEISHU, "lark"))

    assert netloc == "open.larksuite.com"
    assert query["user_code"] == ["JFWX-J2Y5"], "the code must survive the move"


def test_the_user_code_survives():
    """Without it the page has nothing to ack and the link is inert."""
    _, _, _, query = parts(feishu_auth.cli_page_url(LAUNCHER_LARK, "lark"))

    assert query["user_code"] == ["2W9P-M45A"]


def test_the_app_preset_survives():
    """The preset pre-fills the creation form; rebuilding the URL would drop it.

    lark-cli reconstructs the URL from scratch and has no preset to lose. We do,
    which is why this rewrites rather than reconstructs.
    """
    _, _, _, query = parts(feishu_auth.cli_page_url(LAUNCHER_LARK, "lark"))

    assert query["name"] == ["ConnectOnion"]
    assert query["desc"] == ["Receives messages"]


def test_it_identifies_itself_as_this_tool():
    """`from` picks the page's copy; the version marks must not claim to be lark-cli."""
    _, _, _, query = parts(feishu_auth.cli_page_url(LAUNCHER_LARK, "lark"))

    assert query["from"] == ["cli"]
    assert query["lpv"] == ["connectonion"]
    assert query["ocv"] == ["connectonion"]


def test_an_unknown_brand_does_not_crash_the_flow():
    _, netloc, path, query = parts(feishu_auth.cli_page_url(LAUNCHER_LARK, "wat"))

    assert path == "/page/cli"
    assert netloc in {"open.feishu.cn", "open.larksuite.com"}
    assert query["user_code"] == ["2W9P-M45A"]


@pytest.mark.parametrize("url", ["", "not a url at all", "://broken"])
def test_an_unusable_url_is_passed_through_not_mangled(url):
    """Printing what the SDK is actually polling for beats printing nothing."""
    assert feishu_auth.cli_page_url(url, "lark") == url


def test_no_warning_claims_a_live_code_has_expired():
    """The shipped 1.8.5b9 text said this flow could not work on some tenants.

    It can. The cause was the launcher page, not the tenant, and a warning that
    sends people to the Developer Console instead is now false advice.
    """
    source = feishu_auth.__doc__ or ""
    assert not hasattr(feishu_auth, "EXPIRED_MEANS_SOMETHING_ELSE")
    assert "cannot create an application for your" not in source
