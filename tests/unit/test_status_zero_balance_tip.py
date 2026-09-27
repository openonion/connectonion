"""At a zero balance `co status` names the free ways to keep going (#1869).

The owner's design: Gemini 3.8 is the default, and when the credits are gone the
status tip says how to continue for free, with the free managed Gemma or a local
model through Ollama. It used to say only "Low balance! Add credits".
"""

from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from rich.console import Console


def _status(tmp_path, monkeypatch, balance):
    from connectonion.cli.commands import status_commands
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENONION_API_KEY", "token")
    (tmp_path / ".co" / "keys").mkdir(parents=True)
    (tmp_path / ".co" / "keys" / "agent.key").write_text("dummy")
    user = {"balance_usd": balance, "total_cost_usd": 5.0, "credits_usd": 5.0,
            "email": {"address": "me@mail.openonion.ai"}}
    output = StringIO()
    with patch("connectonion.address.load", return_value={"address": "0x1234"}), \
            patch("connectonion.address.sign", return_value=b"\0" * 64), \
            patch.object(status_commands.requests, "post",
                         return_value=Mock(status_code=200, json=lambda: {"user": user})), \
            patch.object(status_commands.requests, "get",
                         return_value=Mock(status_code=200, json=lambda: {"deployments": []})), \
            patch.object(Path, "home", return_value=tmp_path / "home"), \
            patch.object(status_commands, "console",
                         Console(file=output, force_terminal=False, color_system=None, width=140)):
        status_commands.handle_status()
    return output.getvalue()


def test_at_zero_the_tip_names_the_free_models(tmp_path, monkeypatch):
    text = _status(tmp_path, monkeypatch, 0.0)
    assert "co/gemma" in text and "ollama/" in text
    assert "o.openonion.ai/purchase" in text  # adding credits is still one of the ways


def test_with_credits_there_is_no_free_model_tip(tmp_path, monkeypatch):
    text = _status(tmp_path, monkeypatch, 3.5)
    assert "co/gemma" not in text and "ollama/" not in text
