import stat

from connectonion.cli.commands import browser_commands
from connectonion.useful_tools.browser_tools import engine
from connectonion.useful_tools.browser_tools.engine_preferences import (
    load_default_engine,
    save_default_engine,
)


def test_missing_preference_defaults_to_wtfbrowser(tmp_path):
    assert load_default_engine(tmp_path) == engine.WTF


def test_preference_is_canonical_private_and_persistent(tmp_path):
    path = save_default_engine("system", tmp_path)

    assert path.read_text(encoding="utf-8") == "chrome\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load_default_engine(tmp_path) == engine.CHROME


def test_every_chrome_command_prints_detection_and_account_warning(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        browser_commands,
        "send",
        lambda line, **kwargs: calls.append((line, kwargs)) or 0,
    )

    assert browser_commands.handle_browser(["status"], engine_mode="chrome") == 0
    assert browser_commands.handle_browser(["get_current_url"], engine_mode="chrome") == 0

    warning = capsys.readouterr().err
    assert warning.count("WARNING:") == 2
    assert "detect automation" in warning
    assert "suspend accounts" in warning
    assert [kwargs["engine_mode"] for _, kwargs in calls] == ["chrome", "chrome"]
