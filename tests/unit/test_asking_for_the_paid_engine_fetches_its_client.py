"""Asking for the paid engine is asking for the client it runs on.

The documented route to the paid browser was a chain of instructions:

    co browser --engine wtf tab open x
    → BrowserEngineError: onionwright_missing: Run `co browser install-onion`
    → Could not install Onionwright: pip could not install ... (exit 1)

Three commands, and on an externally-managed interpreter the third one failed
too (#1516). The first hop was never carrying its weight: a caller who typed
`--engine wtf` has already said what they want, and the client is not something
they can choose separately — the paid engine cannot run without it.

So the explicit request fetches it. What must NOT change is the rule this
module has always followed: importing ConnectOnion, or taking the free engine,
never mutates a Python environment. Those cases are tested here too, because a
convenience that quietly installs things on people who did not ask is worse
than the extra command it removes.
"""

import pytest

from connectonion.cli.commands import browser_commands
from connectonion.cli.commands import onionwright_install


class _Installed:
    version, already_installed = "0.0.14", False


@pytest.fixture
def spy(monkeypatch):
    """Record what would have been installed and what would have been sent."""
    calls = {"installs": 0, "sent": []}
    monkeypatch.setattr(
        browser_commands, "send", lambda line, **kw: calls["sent"].append(line) or 0
    )
    monkeypatch.setattr(
        onionwright_install,
        "install_onionwright",
        lambda **kw: calls.__setitem__("installs", calls["installs"] + 1) or _Installed(),
    )
    monkeypatch.setenv("CO_DISABLE_TIPS", "1")
    return calls


def _client(monkeypatch, ready: bool):
    monkeypatch.setattr(onionwright_install, "paid_client_is_ready", lambda: ready)


def test_a_missing_client_is_fetched_on_an_explicit_paid_request(spy, monkeypatch):
    _client(monkeypatch, ready=False)

    assert browser_commands.handle_browser(["status"], engine_mode="wtf") == 0

    assert spy["installs"] == 1
    assert spy["sent"] == ["status"], "the command still runs after the fetch"


def test_a_client_already_there_is_not_reinstalled(spy, monkeypatch):
    _client(monkeypatch, ready=True)

    browser_commands.handle_browser(["status"], engine_mode="wtf")

    assert spy["installs"] == 0


@pytest.mark.parametrize("engine", ["auto", "system"])
def test_the_free_engine_never_installs_anything(spy, monkeypatch, engine):
    """The rule that predates this change: no mutation without a paid request."""
    _client(monkeypatch, ready=False)

    browser_commands.handle_browser(["status"], engine_mode=engine)

    assert spy["installs"] == 0
    assert spy["sent"] == ["status"]


def test_help_does_not_install_even_when_the_paid_engine_is_named(spy, monkeypatch):
    """`--engine wtf help` is a question, not a request to run anything."""
    _client(monkeypatch, ready=False)

    browser_commands.handle_browser(["help"], engine_mode="wtf")

    assert spy["installs"] == 0


def test_a_failed_fetch_reports_it_and_does_not_send_the_command(spy, monkeypatch, capsys):
    """A paid command against a missing client must not reach the daemon."""
    _client(monkeypatch, ready=False)
    monkeypatch.setattr(
        onionwright_install,
        "install_onionwright",
        lambda **kw: (_ for _ in ()).throw(
            onionwright_install.OnionwrightInstallError("this Python is externally managed")
        ),
    )

    assert browser_commands.handle_browser(["status"], engine_mode="wtf") == 1

    assert spy["sent"] == [], "nothing may be sent when the engine cannot run"
    assert "externally managed" in capsys.readouterr().err
