"""The paid engine names its cost before spending, and its death names the way back.

From #1510, after 40 minutes on the WTF Browser driving an authenticated Airbnb
host dashboard: "anti-detection was not needed at all ... everything worked
identically *and* the logged-in session survived the restart. So the paid engine
contributed cost and instability and no benefit."

Nothing had said which engine was about to bill. And when the paid session died
mid-task, the error named the reason (`browser_exited`) and no way forward — the
tabs had gone with the session, so the next command failed on a missing tab
instead, which reads like a second, unrelated fault.
"""

import pytest

from connectonion.cli.commands import browser_commands
from connectonion.useful_tools.browser_tools._async_browser import PaidSessionEndedError


@pytest.fixture
def sent(monkeypatch):
    """Run handle_browser without a daemon, recording what it would have sent."""
    calls = []
    monkeypatch.setattr(
        browser_commands, "send", lambda line, **kw: calls.append((line, kw)) or 0
    )
    monkeypatch.setattr(browser_commands, "tips_enabled", lambda: False, raising=False)
    monkeypatch.setenv("CO_DISABLE_TIPS", "1")
    return calls


@pytest.mark.parametrize(
    "args",
    [["tab", "open", "work", "--for", "a task"], ["newtab"], ["open_browser"]],
)
def test_starting_a_paid_session_says_so_first(sent, capsys, args):
    assert browser_commands.handle_browser(list(args), engine_mode="wtf") == 0

    notice = capsys.readouterr().err
    assert "bills" in notice, "the spend must be named before it happens"
    assert "--engine system" in notice, "and the free alternative must be named too"
    assert sent, "the notice must not replace the command"


@pytest.mark.parametrize("args", [["get_text"], ["tab", "ls"], ["status"]])
def test_an_ordinary_command_is_not_nagged(sent, capsys, args):
    """A notice on every command is a notice nobody reads."""
    browser_commands.handle_browser(list(args), engine_mode="wtf")

    assert "bills" not in capsys.readouterr().err


def test_the_free_engine_says_nothing_about_billing(sent, capsys):
    browser_commands.handle_browser(["tab", "open", "work"], engine_mode="system")

    assert "bills" not in capsys.readouterr().err


def test_a_dead_paid_session_names_the_command_that_recovers_it():
    message = str(PaidSessionEndedError("browser_exited"))

    assert "browser_exited" in message, "keep the reason: it is the only upstream fact"
    assert "co browser close" in message
    assert "tab open" in message, "the tabs died with the session; say how to get one back"
    assert "--engine system" in message, "and that the free engine keeps the logins"
