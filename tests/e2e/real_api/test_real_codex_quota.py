"""`co wiki status` reads the owner's real Codex weekly meter (#1843).

Opt-in (real_api): it starts the real `codex app-server` with the real login
under $HOME and asks for `account/rateLimits/read`. No model turn runs, so it
costs no quota. Skips, saying why, where Codex is missing or signed out.
"""

import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.wiki.config import prepare

CODEX_AUTH = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "auth.json"

pytestmark = [
    pytest.mark.skipif(shutil.which("codex") is None, reason="codex is not installed"),
    pytest.mark.skipif(not CODEX_AUTH.is_file(), reason="codex is not signed in"),
]


def test_status_shows_the_real_codex_week(tmp_path):
    root = tmp_path / "wiki"
    prepare(root)  # default runner: codex
    result = CliRunner().invoke(app, ["wiki", "--root", str(root), "--json", "status"])
    assert result.exit_code == 0, result.output
    meter = json.loads(result.stdout)["data"]["quota"]
    assert "unknown" not in meter, meter
    assert type(meter["used_percent"]) is int and 0 <= meter["used_percent"] <= 100
    assert meter["window_minutes"] > 0 and meter["resets_at"] > 0
    assert isinstance(meter["plan"], str) and meter["plan"]
