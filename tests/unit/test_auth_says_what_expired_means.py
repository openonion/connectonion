"""The scan link states its real lifetime, and warns what "Link expired" means.

Measured 2026-09-14 on a JP data-residency Lark tenant. A code issued seconds
earlier, opened once in a browser logged into that tenant:

    go_to    https://open.larksuite.com/page/launcher?user_code=4LLH-3FGX
    current  https://open.larksuite.com/page/launcher       ← user_code gone
    text     Link expired

while the poll endpoint answered `authorization_pending` in the same second.
The code was alive; the page never read it.

Four codes were spent before the word on the screen was doubted, and the reason
it took four is that the command had told the owner the link lasted ten minutes.
It does not: 600 is the SDK's fallback constant for a missing `expires_in`, and
the server returns 3600. A number quoted as measured, that was not, is what sent
an hour into investigating a timeout that never existed.

So: print the server's own number, and say in advance what that page means when
it contradicts it. Two things this must NOT do — both checked rather than
assumed:

  * pretend it can predict the failure. A server-side GET of the launcher
    returns 200 with the code still in the URL; the verdict is rendered after
    the page resolves the browser's tenant.
  * offer `--app-id` as the way around it. That path issues a code from the
    same endpoint and lands on the same launcher, and fails identically.
"""

import pytest

from connectonion.cli.commands import feishu_auth


class FakeRegistration:
    """Stands in for lark_oapi.register_app, carrying a chosen TTL."""

    def __init__(self, expire_in=3600):
        self.expire_in = expire_in

    def __call__(self, on_qr_code, on_status_change=None, **kwargs):
        on_qr_code({
            "url": "https://open.larksuite.com/page/launcher?user_code=ABCD-1234",
            "expire_in": self.expire_in,
        })
        return {"client_id": "cli_new", "client_secret": "s",
                "user_info": {"tenant_brand": "lark"}}


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path / ".co"))
    (tmp_path / ".co").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(feishu_auth, "upsert_env", lambda path, values: None)
    return tmp_path


def run(monkeypatch, expire_in=3600, brand="lark"):
    monkeypatch.setattr(
        feishu_auth, "_register_app", lambda: FakeRegistration(expire_in)
    )
    feishu_auth.handle_feishu_auth(brand=brand)


def test_the_link_states_the_servers_own_lifetime(rig, monkeypatch, capsys):
    run(monkeypatch, expire_in=3600)

    out = capsys.readouterr().out
    assert "60 minutes" in out
    assert "3600s" in out


def test_a_different_lifetime_is_reported_as_that(rig, monkeypatch, capsys):
    """Nothing is hardcoded: whatever the platform says is what is shown."""
    run(monkeypatch, expire_in=900)

    assert "15 minutes" in capsys.readouterr().out


def test_an_absent_lifetime_says_so_instead_of_guessing(rig, monkeypatch, capsys):
    """The SDK's 600 fallback is exactly what must never be quoted as fact."""
    run(monkeypatch, expire_in=None)

    out = capsys.readouterr().out
    assert "did not say how long" in out
    assert "10 minutes" not in out
    assert "600" not in out


def test_it_warns_that_expired_can_mean_the_tenant_not_the_clock(rig, monkeypatch, capsys):
    run(monkeypatch)

    out = capsys.readouterr().out
    assert "Link expired" in out
    assert "still alive" in out
    assert "data-residency" in out


def test_it_does_not_offer_app_id_as_the_way_around_this(rig, monkeypatch, capsys):
    """--app-id uses the same launcher and fails the same way (checked).

    A remedy that cannot work is worse than none: it sends the reader in a
    circle with the confidence of an instruction.
    """
    run(monkeypatch)

    out = capsys.readouterr().out
    warning = out[out.index("Link expired"):]
    assert "co auth lark --app-id" not in warning
    assert "co auth feishu --app-id" not in warning
    assert "fails the same way" in warning


def test_the_warning_names_where_the_evidence_is(rig, monkeypatch, capsys):
    run(monkeypatch)

    assert "issues/1537" in capsys.readouterr().out


def test_the_link_itself_is_still_printed_first(rig, monkeypatch, capsys):
    """A warning must not bury the thing the person came for."""
    out = capsys.readouterr().out
    run(monkeypatch)
    out = capsys.readouterr().out

    assert out.index("page/launcher?user_code=ABCD-1234") < out.index("Link expired")


@pytest.mark.parametrize(
    "seconds,expected", [(3600, "60 minutes"), (900, "15 minutes"), (60, "60s")]
)
def test_link_life_formats_what_it_was_given(seconds, expected):
    assert expected in feishu_auth._link_life(seconds)


def test_link_life_refuses_to_invent_a_number():
    for bad in (None, "", "soon"):
        assert "did not say" in feishu_auth._link_life(bad)
