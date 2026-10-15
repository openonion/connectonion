"""Collection failures are real failed passes, before any model has run."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from httplib2 import Response, ServerNotFoundError
from connectonion.provider_credentials import ProviderCredentialError

import pytest

from connectonion.rem import service
from connectonion.rem.config import prepare, read_config
from connectonion.rem.files import RemError, read_json, state_path, write_json


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
    write_json(state_path(root, "consent.json"), {})
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "fixture"})
    progress = {"codex": {"rollout-fixture.jsonl": {"offset": 10, "digest": "old"}}}
    write_json(state_path(root, "progress.json"), progress)
    monkeypatch.setattr(service, "_selected_sources", lambda *a: {"codex": {"kind": "codex"}})
    monkeypatch.setattr(service, "_resume_archive", lambda *a: pytest.fail("archive must not resume after failed gathering"))
    moment = datetime(2026, 10, 15, 8, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "now", lambda: moment)
    monkeypatch.setattr(service, "latest_slot", lambda *a: moment)
    return root, progress


@pytest.mark.parametrize("error", [RemError("Invalid session metadata"), OSError("private provider detail"),
                                   UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")])
def test_collection_failure_is_logged_without_advancing_or_running_model(notebook, monkeypatch, error):
    root, progress = notebook
    def collect(*args):
        raise error
    monkeypatch.setattr(service, "collect", collect)
    result = service.run_sync(root, runner=lambda *a, **k: pytest.fail("model must not run"))
    assert result["outcome"] == "failed"
    assert result["stage"] == "gathering sources"
    assert result["failed_source"] == "codex"
    assert result["runner_attempts"] == 0 and result["changed"] == []
    assert result["finished_at"] and result["seconds"] == 0
    logs = service.run_logs(root)
    assert len(logs) == 1 and logs[0]["id"] == result["id"]
    assert logs[0]["outcome"] == "failed" and logs[0]["failed_source"] == "codex"
    assert read_json(state_path(root, "progress.json"), {}) == progress
    assert "private provider detail" not in result["error"]


def test_scheduled_collection_failure_serves_one_slot_and_reports_attention(notebook, monkeypatch):
    root, _ = notebook
    calls = []
    def collect(*args):
        calls.append(True)
        raise RemError("Invalid session metadata")
    monkeypatch.setattr(service, "collect", collect)
    assert service.run_sync(root, scheduled=True)["outcome"] == "failed"
    assert service.run_sync(root, scheduled=True) is None
    assert calls == [True]
    worker = service.worker_state(root)
    assert worker["last_scheduled_outcome"] == "failed"
    state, _ = service._state_line(root, read_config(root), ZoneInfo("UTC"))
    assert state.startswith("Background needs attention")
    assert "Invalid session metadata" in state and "co rem logs" in state


@pytest.mark.parametrize("error", [RemError("Outlook could not be read"),
    httpx.ConnectError("private provider detail"), httpx.ReadTimeout("private provider detail"),
    ProviderCredentialError("expired", "Mailbox authorization expired", "co auth microsoft"),
    HttpError(Response({"status": "503"}), b"private provider detail"),
    RefreshError("private provider detail"), ServerNotFoundError("private provider detail")])
def test_mail_collection_failure_is_not_lost_before_record_creation(notebook, monkeypatch, error):
    root, _ = notebook
    monkeypatch.setattr(service, "_selected_sources", lambda *a: {"outlook": {"kind": "outlook"}})
    monkeypatch.setattr(service, "mail_client", lambda *a: object())
    def collect(*args, **kwargs):
        raise error
    monkeypatch.setattr(service, "collect_mail", collect)
    result = service.run_sync(root)
    assert result["outcome"] == "failed" and result["failed_source"] == "outlook"
    assert service.run_logs(root)[0]["error"] == result["error"]
    assert "private provider detail" not in result["error"]
    if isinstance(error, ProviderCredentialError):
        assert "co auth microsoft" in result["error"]


def test_programmer_errors_are_not_disguised_as_source_failures(notebook, monkeypatch):
    root, _ = notebook
    def collect(*args):
        raise TypeError("collector bug")
    monkeypatch.setattr(service, "collect", collect)
    with pytest.raises(TypeError, match="collector bug"):
        service.run_sync(root)


@pytest.mark.parametrize("as_json", [False, True])
def test_cli_reports_collection_failure_as_nonzero(notebook, monkeypatch, as_json):
    import json
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    root, _ = notebook
    def collect(*args):
        raise RemError("Invalid session metadata")
    monkeypatch.setattr(service, "collect", collect)
    args = ["rem", "--root", str(root), *(["--json"] if as_json else []), "sync"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1, result.output
    if as_json:
        value = json.loads(result.stdout)
        assert value["ok"] is False
        assert value["data"]["maintenance"]["failed_source"] == "codex"
    else:
        assert "Invalid session metadata" in result.output


def test_scheduled_daily_pass_keeps_collection_reason_and_does_not_investigate(notebook, monkeypatch):
    from connectonion.rem.daily import run_daily
    root, _ = notebook
    calls = []
    def collect(*args):
        calls.append(True)
        raise RemError("Invalid session metadata")
    monkeypatch.setattr(service, "collect", collect)
    result = run_daily(root, scheduled=True,
                       investigate_one=lambda *a, **k: pytest.fail("investigation must not run"))
    assert result["outcome"] == "partial" and result["investigation"] is None
    assert service.worker_state(root)["last_scheduled_reason"] == "Invalid session metadata"
    assert run_daily(root, scheduled=True) is None and calls == [True]


@pytest.mark.parametrize("kind,command", [("gmail", "co auth google"), ("outlook", "co auth microsoft")])
def test_mail_client_validation_is_recorded_with_safe_recovery(notebook, monkeypatch, kind, command):
    root, _ = notebook
    monkeypatch.setattr(service, "_selected_sources", lambda *a: {kind: {"kind": kind}})
    def client(*args):
        raise ValueError("private configuration detail")
    monkeypatch.setattr(service, "mail_client", client)
    result = service.run_sync(root)
    assert result["outcome"] == "failed" and result["failed_source"] == kind
    assert command in result["error"] and "private configuration detail" not in result["error"]
