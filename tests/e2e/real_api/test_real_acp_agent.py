"""Real pinned-adapter checks for the generic downward ACP edge.

Run explicitly because these tests invoke authenticated provider CLIs:

    pytest -m real_api tests/e2e/real_api/test_real_acp_agent.py
"""

import json
import os
import shutil
import sys

import pytest

from connectonion.useful_tools.acp_agent import ACPAgent

pytestmark = [pytest.mark.real_api, pytest.mark.provider_cli]
HAS_NPX = shutil.which("npx") is not None
REAL_CODEX_HOME = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
HAS_CODEX_AUTH = bool(
    os.environ.get("CODEX_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or os.path.isfile(os.path.join(REAL_CODEX_HOME, "auth.json"))
)
HAS_CLAUDE = bool(os.environ.get("CLAUDE_CODE_CMD") or shutil.which("claude"))
REAL_PROVIDER_HOME = os.path.expanduser("~")
REAL_CLAUDE_CONFIG_DIR = os.environ.get("CLAUDE_CONFIG_DIR")
HAS_GEMINI_ENV_AUTH = bool(
    os.environ.get("GEMINI_API_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
)
HAS_GEMINI_AUTH = bool(
    HAS_GEMINI_ENV_AUTH
    or os.path.isfile(os.path.expanduser("~/.gemini/oauth_creds.json"))
)

requires_npx = pytest.mark.skipif(not HAS_NPX, reason="npx is not installed")


@pytest.fixture
def real_codex_home(monkeypatch):
    """Opt-in Codex tests may read CLI auth without exposing the whole HOME."""
    monkeypatch.setenv("CODEX_HOME", REAL_CODEX_HOME)


@pytest.fixture
def real_claude_config(monkeypatch):
    """Opt-in tests expose only the platform's native Claude auth source."""
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    environment = _real_claude_auth_environment(
        sys.platform, REAL_PROVIDER_HOME, REAL_CLAUDE_CONFIG_DIR
    )
    for key, value in environment.items():
        monkeypatch.setenv(key, value)


def _real_claude_auth_environment(
    platform: str, home: str, configured_dir: str | None
) -> dict[str, str]:
    if configured_dir:
        return {"CLAUDE_CONFIG_DIR": configured_dir}
    if platform == "darwin":
        return {"HOME": home}
    return {"CLAUDE_CONFIG_DIR": os.path.join(home, ".claude")}


def _real_gemini_auth_environment(
    home: str, has_explicit_auth: bool
) -> dict[str, str]:
    return {} if has_explicit_auth else {"HOME": home}


@pytest.fixture
def real_gemini_auth(monkeypatch):
    """OAuth-only tests expose Gemini's real credential home."""
    for key, value in _real_gemini_auth_environment(
        REAL_PROVIDER_HOME, HAS_GEMINI_ENV_AUTH
    ).items():
        monkeypatch.setenv(key, value)


def _success(output: str) -> dict:
    result = json.loads(output)
    assert "error" not in result, result.get("error")
    assert result["session_id"]
    assert result["stop_reason"]
    return result


@requires_npx
@pytest.mark.skipif(not HAS_CODEX_AUTH, reason="Codex CLI is not authenticated")
def test_real_codex_acp_auto_turn_and_resume(tmp_path, real_codex_home):
    tool = ACPAgent(approval="auto", workspace=tmp_path)
    first = _success(
        tool.acp_agent(
            "Remember the number 23 and reply exactly ACP_CODEX_FIRST_23.",
            engine="codex",
            timeout=180,
        )
    )
    assert first["result"].strip() == "ACP_CODEX_FIRST_23"

    second = _success(
        tool.acp_agent(
            "Reply exactly ACP_CODEX_RESUME_<the remembered number>.",
            engine="codex",
            session_id=first["session_id"],
            timeout=180,
        )
    )
    assert second["resumed"] is True
    assert second["session_id"] == first["session_id"]
    assert second["result"].strip() == "ACP_CODEX_RESUME_23"


@requires_npx
@pytest.mark.skipif(not HAS_CLAUDE, reason="Claude Code CLI is not installed")
def test_real_claude_acp_manual_turn_and_resume(tmp_path, real_claude_config):
    tool = ACPAgent(approval="manual", workspace=tmp_path)
    first = _success(
        tool.acp_agent(
            "Remember the number 31 and reply exactly ACP_CLAUDE_FIRST_31.",
            engine="claude-code",
            timeout=180,
        )
    )
    assert first["result"].strip() == "ACP_CLAUDE_FIRST_31"

    second = _success(
        tool.acp_agent(
            "Reply exactly ACP_CLAUDE_RESUME_<the remembered number>.",
            engine="claude-code",
            session_id=first["session_id"],
            timeout=180,
        )
    )
    assert second["resumed"] is True
    assert second["session_id"] == first["session_id"]
    assert second["result"].strip() == "ACP_CLAUDE_RESUME_31"


@requires_npx
@pytest.mark.skipif(not HAS_GEMINI_AUTH, reason="Gemini CLI is not authenticated")
def test_real_gemini_acp_manual_turn(tmp_path, real_gemini_auth):
    tool = ACPAgent(approval="manual", workspace=tmp_path)
    result = json.loads(
        tool.acp_agent(
            "Reply exactly ACP_GEMINI_ONE_TURN_OK.", engine="gemini", timeout=180
        )
    )
    assert "error" not in result, result.get("error")
    assert result["session_id"] == ""
    assert result["resumed"] is False
    assert result["stop_reason"]
    assert result["result"].strip() == "ACP_GEMINI_ONE_TURN_OK"
