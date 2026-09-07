"""Opt-in real Claude Code CLI checks.

Run with an installed/authenticated CLI:

    pytest -m real_api tests/e2e/real_api/test_real_claude_code.py
"""

import json
import os
import shutil
import sys

import pytest

from connectonion.useful_tools import claude_code

pytestmark = [pytest.mark.real_api, pytest.mark.provider_cli]
HAS_CLAUDE = bool(os.environ.get("CLAUDE_CODE_CMD") or shutil.which("claude"))
REAL_CLAUDE_HOME = os.path.expanduser("~")
REAL_CLAUDE_CONFIG_DIR = os.environ.get("CLAUDE_CONFIG_DIR")
requires_claude = pytest.mark.skipif(
    not HAS_CLAUDE, reason="Claude Code CLI is not installed"
)


def _real_claude_auth_environment(
    platform: str, home: str, configured_dir: str | None
) -> dict[str, str]:
    if configured_dir:
        return {"CLAUDE_CONFIG_DIR": configured_dir}
    if platform == "darwin":
        return {"HOME": home}
    return {"CLAUDE_CONFIG_DIR": os.path.join(home, ".claude")}


@pytest.fixture(autouse=True)
def _use_real_claude_auth(monkeypatch):
    """Opt-in real tests expose only the platform's real Claude auth source."""
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    environment = _real_claude_auth_environment(
        sys.platform, REAL_CLAUDE_HOME, REAL_CLAUDE_CONFIG_DIR
    )
    for key, value in environment.items():
        monkeypatch.setenv(key, value)


def _require_success(result):
    if result["status"] == "completed":
        return
    pytest.fail(result["error"])


@requires_claude
def test_real_claude_code_stream_contract(tmp_path):
    result = json.loads(
        claude_code("Reply with exactly: pong", cwd=str(tmp_path), timeout=120)
    )

    assert result["provider"] == "claude_code"
    _require_success(result)
    assert result["session_id"]
    assert "pong" in result["result"].lower()


@requires_claude
def test_real_claude_code_session_resume(tmp_path):
    first = json.loads(
        claude_code("Remember the number 7.", cwd=str(tmp_path), timeout=120)
    )
    _require_success(first)

    second = json.loads(
        claude_code(
            "What number did I ask you to remember?",
            session_id=first["session_id"],
            cwd=str(tmp_path),
            timeout=120,
        )
    )
    _require_success(second)
    assert second["resumed"] is True
    assert second["session_id"] == first["session_id"]
    assert "7" in second["result"]
