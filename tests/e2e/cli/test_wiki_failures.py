"""Failure paths through the real CLI process: each names its cause and a next command.

None of these reach a model, so they need no login and no codex binary and
run in CI. What they check is what a user sees when the environment is wrong.
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from connectonion.wiki.config import prepare
from connectonion.wiki.service import approve_sources


@pytest.fixture
def consented(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "rollout-a.jsonl").write_text(
        '{"type": "session_meta", "payload": {"id": "s", "cwd": "/work"}}\n'
        '{"timestamp": "2099-01-01T00:00:00Z", "type": "response_item", "payload": {"type": "message", '
        '"role": "user", "content": [{"type": "input_text", "text": "hello"}]}}\n')
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: sessions)
    root = tmp_path / "wiki"
    prepare(root)
    approve_sources(root)
    return root


def co(root, *args, env):
    result = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "wiki", "--root", str(root),
                             "--json", *args], capture_output=True, text=True, env=env, timeout=120)
    payload = json.loads(result.stdout) if result.stdout.strip() else {}
    return result.returncode, payload, result.stderr


def test_missing_login_names_codex_login(consented, tmp_path):
    empty_home = tmp_path / "empty-codex-home"
    empty_home.mkdir()
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "CODEX_HOME": str(empty_home),
           "PYTHONPATH": str(Path(__file__).resolve().parents[3])}
    code, payload, stderr = co(consented, "sync", env=env)
    assert code == 1, stderr
    assert "codex login" in payload["data"], payload
    assert "co wiki" in payload["next"]
    assert not list((consented / ".state").glob("runs/*.json"))  # no attempt of the day was spent


def test_missing_codex_binary_names_install(consented, tmp_path):
    """A real login, so the missing binary is what the message is about."""
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "auth.json").write_text(json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": "x"}}))
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "CODEX_HOME": str(home),
           "PYTHONPATH": str(Path(__file__).resolve().parents[3])}
    code, payload, stderr = co(consented, "sync", env=env)
    assert code == 1, stderr
    assert "Codex CLI is missing" in payload["data"], payload
    assert not list((consented / ".state").glob("runs/*.json"))  # preflight, not a failed batch


def test_second_sync_while_one_runs_says_busy(consented, tmp_path):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "PYTHONPATH": str(Path(__file__).resolve().parents[3])}
    holder = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import time
        from pathlib import Path
        from connectonion.wiki.files import maintenance_lock
        with maintenance_lock(Path({str(consented)!r})):
            print("held", flush=True); time.sleep(30)
    """)], stdout=subprocess.PIPE, text=True, env=env)
    try:
        assert holder.stdout.readline().strip() == "held"
        code, payload, stderr = co(consented, "sync", env=env)
        assert code == 1, stderr
        assert "busy" in payload["data"].lower(), payload
        assert "co wiki" in payload["next"]
    finally:
        holder.kill()


def test_a_batch_that_fails_past_preflight_exits_nonzero_and_is_logged(consented, tmp_path):
    """Past preflight, a failure is a real attempt: recorded, counted, and exit 1.

    A credential that says it is a ChatGPT login but carries a dead token passes
    preflight -- the file is there, it names the right billing, the binary is
    there -- and fails inside the native handshake, which is what an expired
    login looks like. (An empty `{}` no longer reaches here: preflight now reads
    the file rather than only checking that it exists.)"""
    import shutil
    codex = shutil.which("codex")
    if not codex:
        pytest.skip("needs the codex binary on PATH")
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "auth.json").write_text(json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": "dead"}}))
    env = {"PATH": f"{Path(codex).parent}:/usr/bin:/bin", "HOME": str(tmp_path), "CODEX_HOME": str(home),
           "PYTHONPATH": str(Path(__file__).resolve().parents[3])}
    code, payload, stderr = co(consented, "sync", env=env)
    assert code == 1, stderr
    assert "failed" in payload["data"].lower() and "run_" in payload["data"], payload
    runs = list((consented / ".state" / "runs").glob("*.json"))
    assert len(runs) == 1 and json.loads(runs[0].read_text())["outcome"] == "failed"
    assert "dead" not in payload["data"]  # nothing from the credential file is echoed
