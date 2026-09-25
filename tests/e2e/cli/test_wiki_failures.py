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


def test_no_co_on_path_still_runs_this_installation(consented, tmp_path):
    """Model turns go to the running installation's `co ai`, so a PATH without
    any `co` no longer matters; the failure here is COAI's own, not a lookup."""
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
           "PYTHONPATH": str(Path(__file__).resolve().parents[3])}
    code, payload, stderr = co(consented, "sync", env=env)
    assert code == 1, stderr
    record = json.loads(next((consented / ".state" / "runs").glob("*.json")).read_text())
    assert "codex CLI not found" in record["error"], record
    assert not (consented / ".state" / "progress.json").exists()


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
    """COAI owns provider errors; Wiki records the failed attempt and preserves progress.

    The `co` earlier on PATH is a decoy: it must not answer. A tester's older
    ~/.local/bin/co did answer every model turn on 1.8.8b7 (see co_command)."""
    binary = tmp_path / "bin"
    binary.mkdir()
    (binary / "co").write_text(
        '#!/bin/sh\necho \'{"outcome":"error","error":"Login required; run codex login"}\'\nexit 1\n')
    (binary / "co").chmod(0o755)
    env = {"PATH": f"{binary}:/usr/bin:/bin", "HOME": str(tmp_path),
           "PYTHONPATH": str(Path(__file__).resolve().parents[3])}
    code, payload, stderr = co(consented, "sync", env=env)
    assert code == 1, stderr
    # `sync` is the whole update now (#1656): a failed first batch is a partial round.
    assert payload["data"]["outcome"] == "partial", payload
    assert payload["data"]["maintenance"]["outcome"] == "failed" and payload["data"]["maintenance"]["id"].startswith("run_")
    runs = list((consented / ".state" / "runs").glob("*.json"))
    record = json.loads(runs[0].read_text())
    assert len(runs) == 1 and record["outcome"] == "failed"
    assert "codex CLI not found" in record["error"] and "codex login" not in record["error"]
    assert not (consented / ".state" / "progress.json").exists()
