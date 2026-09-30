"""`co status` is on the shared look (#2008): no emoji panel, a Next line at the end.

It kept a cyan panel titled "📊 Account Status" and ended on a 💡 tip after
every other command moved onto connectonion/cli/style.py (#1997).
"""

from test_status_zero_balance_tip import _status


def test_the_account_is_a_section_not_an_emoji_panel(tmp_path, monkeypatch, capsys):
    text = _status(tmp_path, monkeypatch, 3.0)
    assert "📊" not in text and "╭" not in text
    assert "Account\n" in text and "  Balance: $3.0000" in text


def test_it_ends_on_a_next_line_naming_a_command(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("CO_TIPS", raising=False)
    _status(tmp_path, monkeypatch, 3.0)
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith("Next: ") and " co " in last and "💡" not in last


def test_no_api_key_names_the_command_to_run(tmp_path, monkeypatch, capsys):
    from connectonion.cli.commands import status_commands
    monkeypatch.setattr(status_commands, "_show_credentials", lambda reveal=False: None)
    monkeypatch.setattr(status_commands, "load_api_key", lambda: None)
    status_commands.handle_status()
    out = capsys.readouterr().out
    assert "No API key found" in out and out.strip().splitlines()[-1] == "Next: co auth"
    assert "❌" not in out
