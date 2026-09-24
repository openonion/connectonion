"""An explicit --no-headless gets a window or a refusal, never headless (#1339).

The option defaulted to False, so `--no-headless` and saying nothing were the
same value, and on Linux with no display both were turned into headless.
Headless Chrome puts `HeadlessChrome` in its User-Agent — the thing a caller
asking for a window was avoiding — and nothing said the mode had changed.
"""

import pytest
from typer.testing import CliRunner

from connectonion.cli import main as cli_main
from connectonion.cli.commands import browser_commands
from connectonion.useful_tools.browser_tools import _async_browser


@pytest.fixture
def launched(monkeypatch):
    seen = []
    monkeypatch.setattr(browser_commands, "handle_browser",
                        lambda args, headless, engine_mode: seen.append(headless) or 0)
    monkeypatch.setattr("connectonion.useful_tools.browser_tools.engine.effective_mode",
                        lambda engine: "system")
    return seen


def no_display(monkeypatch):
    monkeypatch.setattr(_async_browser.platform, "system", lambda: "Linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)


def test_explicit_no_headless_without_a_display_is_refused(monkeypatch, launched):
    no_display(monkeypatch)

    result = CliRunner().invoke(cli_main.app, ["browser", "--no-headless", "status"])

    assert result.exit_code == 2
    assert "needs a display" in result.output
    assert "xvfb-run -a co browser --no-headless" in result.output
    assert launched == []                       # nothing started


def test_saying_nothing_still_falls_back_to_headless(monkeypatch, launched):
    no_display(monkeypatch)

    result = CliRunner().invoke(cli_main.app, ["browser", "status"])

    assert result.exit_code == 0
    assert launched == [False]                  # the browser layer decides
    assert _async_browser._headless_without_display(False) is True


def test_explicit_no_headless_with_a_display_runs_headed(monkeypatch, launched):
    monkeypatch.setattr(_async_browser.platform, "system", lambda: "Linux")
    monkeypatch.setenv("DISPLAY", ":99")

    result = CliRunner().invoke(cli_main.app, ["browser", "--no-headless", "status"])

    assert result.exit_code == 0
    assert launched == [False]
    assert _async_browser._headless_without_display(False) is False
