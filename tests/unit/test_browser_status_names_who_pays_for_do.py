"""`co browser status` does not say whose credits `do` spends (#728).

The daemon is shared and long-lived by design, and `do` runs the agent inside
it, so the model is paid for out of the daemon's environment — not the caller's.
Running `do` from a worktree whose .env holds my machine key (balance $711):

    ❌ Insufficient ConnectOnion Credits
    Account:     0x561605f3...dbe4
    Balance:     $-0.0702

    daemon cwd        /Users/changxing/project/OnCourse/platform  (another session)
    that dir's .env   account 0x561605f3
    my worktree .env  account 0x10e68f6d, $711

An account the reader has nothing to do with, named by an error they cannot
place. Every page verb — go_to, click, get_text — touches no model and is free
of this; only `do` spends.

#728 lists three shapes for the underlying behaviour. This is the smallest of
them: leave the billing alone and stop it being a surprise, by naming the payer
where people already look for browser state. Whether `do` *should* charge the
caller instead is a decision about what the shared daemon is, and is not made
here.

The address is public — it is what an agent announces to the relay — so this
prints no secret. The key itself is never shown.
"""

import pytest


class _Browser:
    """Every attribute _status actually reaches for.

    The first version left out `tab_status`, which _status calls on its last
    line — a stand-in that agreed with the test and not with the thing. Kept
    minimal but complete: if _status starts using something else, this fails
    loudly rather than passing on a fake that has drifted.
    """

    _headless = False
    _tab_meta = {}

    def _context_is_alive(self):
        return True

    def tab_status(self):
        return "Tabs (1):\n  *[main]"


@pytest.fixture
def daemon(monkeypatch):
    from connectonion.cli.browser_agent import daemon as mod

    instance = mod.BrowserDaemon.__new__(mod.BrowserDaemon)
    instance.browser = _Browser()
    instance.last_command = None
    monkeypatch.setattr(
        mod, "driver_stealth_status", lambda: ("ok", "1.61.2", "stealth patches present")
    )
    return mod, instance


def _status_text(daemon):
    _, instance = daemon
    _, payload = instance._status()
    return payload


class TestItNamesThePayer:

    def test_the_account_appears(self, daemon, monkeypatch):
        mod, instance = daemon
        monkeypatch.setattr(
            mod, "_daemon_account", lambda: "0x561605f3ab12cd34ef56ab78cd90ef12dbe4"
        )

        assert "0x561605f3" in _status_text(daemon)

    def test_it_says_what_the_account_is_for(self, daemon, monkeypatch):
        mod, instance = daemon
        monkeypatch.setattr(mod, "_daemon_account", lambda: "0x" + "a" * 64)

        text = _status_text(daemon).lower()

        assert "do" in text and ("pays" in text or "billed" in text or "charged" in text)

    def test_the_key_itself_is_never_printed(self, daemon, monkeypatch):
        mod, instance = daemon
        monkeypatch.setenv("OPENONION_API_KEY", "eyJhbGciOiJIUzI1NiJ9.secret.sig")
        monkeypatch.setattr(mod, "_daemon_account", lambda: "0x" + "b" * 64)

        text = _status_text(daemon)

        assert "eyJhbGci" not in text
        assert "secret" not in text


class TestItStaysQuietWhenThereIsNothingToName:

    def test_no_account_no_line(self, daemon, monkeypatch):
        mod, instance = daemon
        monkeypatch.setattr(mod, "_daemon_account", lambda: None)

        text = _status_text(daemon).lower()

        assert "pays" not in text and "billed" not in text

    def test_the_rest_of_status_is_unchanged(self, daemon, monkeypatch):
        mod, instance = daemon
        monkeypatch.setattr(mod, "_daemon_account", lambda: None)

        text = _status_text(daemon)

        assert "Browser: open" in text
        assert "Stealth driver" in text


class TestReadingTheAccountNeverBreaksStatus:
    """Status is what you run when things are wrong; it must not add a way to
    fail."""

    def test_an_unreadable_identity_is_not_an_error(self, daemon, monkeypatch):
        mod, instance = daemon

        def explode():
            raise OSError("permission denied")

        monkeypatch.setattr(mod, "_daemon_account", explode)

        assert "Browser: open" in _status_text(daemon)
