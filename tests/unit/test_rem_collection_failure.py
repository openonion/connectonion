"""Source failures stay visible while healthy sources continue."""
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
    config = read_config(root)
    assert (result["harness"], result["model"], result["speed"]) == (config["runner"], config["model"], "fast")
    assert result["stage"] == "gathering sources"
    assert result["failed_source"] == "codex"
    assert result["runner_attempts"] == 0 and result["changed"] == []
    assert result["finished_at"] and result["seconds"] == 0
    logs = service.run_logs(root)
    assert len(logs) == 1 and logs[0]["id"] == result["id"]
    assert logs[0]["outcome"] == "failed" and logs[0]["failed_source"] == "codex"
    assert read_json(state_path(root, "progress.json"), {}) == {**progress, "rem_last_source": "codex"}
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
    assert service.worker_state(root)["last_scheduled_reason"] == "Codex read failed: RemError Invalid session metadata"
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


class FailingMailbox:
    def my_addresses(self):
        raise HttpError(Response({"status": "503"}),
                        b'{"error": {"message": "Backend Error"}}',
                        uri="https://example.com/mail?access_token=secret-token")


@pytest.fixture
def mixed_sources(notebook, monkeypatch):
    from connectonion.rem.source import Batch
    root, progress = notebook
    sources = {
        "gmail": {"kind": "gmail", "enabled": True, "consented": True,
                  "since": "2026-10-01T00:00:00+00:00"},
        "codex": {"kind": "codex"},
    }
    progress["gmail"] = {"scanned_until": "2026-10-10T00:00:00+00:00"}
    write_json(state_path(root, "progress.json"), progress)
    write_json(state_path(root, "subscriptions.json"), sources)
    monkeypatch.setattr(service, "_selected_sources", lambda *a: sources)
    monkeypatch.setattr(service, "mail_available", lambda kind: kind == "gmail")
    monkeypatch.setattr(service, "mail_client", lambda *a: FailingMailbox())
    item = {"source": "codex:fixture", "text": "Choose a local notebook", "role": "user"}
    monkeypatch.setattr(service, "collect", lambda *a: Batch([item], {"offset": 20}))
    return root, progress, sources, item


def test_http_failure_continues_to_other_source_and_status_reports_it(mixed_sources):
    from rich.text import Text
    from connectonion.cli.commands.rem_status import _mailboxes
    root, before, sources, item = mixed_sources
    gathered = []
    result = service.run_sync(root, runner=lambda book, items, config, **kw:
                              gathered.extend(items) or {"changed": []})
    assert gathered == [item]
    assert result["outcome"] == "completed"
    assert result["failed_source"] == "gmail"
    assert result["source_failures"] == [{"source": "gmail", "error": "Gmail read failed: HttpError 503 Backend Error"}]
    assert "gmail" in result["warning"]
    assert result["error"] == "Gmail read failed: HttpError 503 Backend Error"
    after = read_json(state_path(root, "progress.json"), {})
    assert after["gmail"] == before["gmail"]
    assert after["codex"] == {"offset": 20}
    assert list(service._rotated(sources, after["rem_last_source"])) == ["gmail", "codex"]
    assert service.run_logs(root)[0]["source_failures"] == result["source_failures"]
    state = service.status(root)["mailboxes"]["gmail"]
    assert "last read failed 2026-10-15" in state and "HttpError 503 Backend Error" in state
    rendered = Text.from_markup("\n".join(_mailboxes(root))).plain
    assert "✗ Gmail" in rendered and "last read failed" in rendered
    assert "✓ Gmail" not in rendered


def test_failed_source_advances_rotation_even_when_all_reads_fail(mixed_sources, monkeypatch):
    root, before, sources, _ = mixed_sources
    sources.clear()
    sources["gmail"] = {"kind": "gmail", "enabled": True, "consented": True}
    result = service.run_sync(root)
    assert result["outcome"] == "failed"
    after = read_json(state_path(root, "progress.json"), {})
    assert after["gmail"] == before["gmail"]
    assert after["rem_last_source"] == "gmail"
    assert result["error"] == "Gmail read failed: HttpError 503 Backend Error"


def test_multiple_failures_keep_each_reason_and_read_the_next_source(mixed_sources, monkeypatch):
    from connectonion.cli.commands.rem_output import sync_summary
    from rich.text import Text
    root, _, sources, item = mixed_sources
    sources["outlook"] = {"kind": "outlook", "enabled": True, "consented": True}
    sources["codex"] = sources.pop("codex")
    result = service.run_sync(root, runner=lambda *a, **kw: {"changed": []})
    assert result["outcome"] == "completed" and result["items"] == 1
    assert [row["source"] for row in result["source_failures"]] == ["gmail", "outlook"]
    assert all(name in result["warning"] for name in ("gmail", "outlook"))
    rendered = Text.from_markup(sync_summary(result)).plain
    assert "Gmail read failed: HttpError 503 Backend Error" in rendered
    assert "Outlook read failed: HttpError 503 Backend Error" in rendered


def test_successful_empty_read_completes_with_warning_and_clears_old_failure(mixed_sources, monkeypatch):
    from connectonion.rem.source import Batch
    root, _, sources, _ = mixed_sources
    monkeypatch.setattr(service, "collect", lambda *a: Batch([], {"offset": 20}))
    result = service.run_sync(root)
    assert result["outcome"] == "completed" and result["runner_attempts"] == 0
    assert "gmail" in result["warning"]
    monkeypatch.setattr(service, "collect_mail", lambda *a, **kw:
                        Batch([], {"scanned_until": service.now().isoformat()}))
    monkeypatch.setattr(service, "_resume_archive", lambda *a: None)
    service.run_sync(root)
    assert service.status(root)["mailboxes"]["gmail"] == "read by the daily round"


@pytest.mark.parametrize("days,sync_ran,unhealthy", [(3, True, True), (2, True, False), (3, False, False)])
def test_status_marks_stale_mailbox_only_when_syncs_ran(mixed_sources, days, sync_ran, unhealthy):
    from datetime import timedelta
    root, progress, _, _ = mixed_sources
    scanned = service.now() - timedelta(days=days)
    progress["gmail"]["scanned_until"] = scanned.isoformat()
    write_json(state_path(root, "progress.json"), progress)
    if sync_ran:
        write_json(state_path(root, "runs/run_fixture.json"), {
            "id": "run_fixture", "phase": "sync", "started_at": service.now().isoformat(),
            "outcome": "completed", "items_by_source": {"codex": 1}})
    state = service.status(root)["mailboxes"]["gmail"]
    assert ("last read failed" in state) == unhealthy
    if unhealthy:
        assert str(scanned.date()) in state and "scan is more than 2 days behind" in state


def test_status_recognises_failure_records_from_before_upgrade(mixed_sources):
    root, _, _, _ = mixed_sources
    write_json(state_path(root, "runs/run_fixture.json"), {
        "id": "run_fixture", "phase": "sync", "started_at": service.now().isoformat(),
        "outcome": "failed", "failed_source": "gmail", "error": "Source collection failed (HttpError)"})
    assert "last read failed 2026-10-15" in service.status(root)["mailboxes"]["gmail"]


@pytest.mark.parametrize("error", [
    HttpError(Response({"status": "503"}),
              b'{"error": {"message": "Backend Error for person@example.com token=secret-token body: private body"}}'),
    OSError("Connection refused person@example.com token=secret-token body: private body"),
])
def test_collection_diagnostics_never_copy_mail_or_credentials(mixed_sources, monkeypatch, error):
    import json
    root, _, _, _ = mixed_sources
    def client(*a):
        raise error
    monkeypatch.setattr(service, "mail_client", client)
    result = service.run_sync(root, runner=lambda *a, **kw: {"changed": []})
    assert result["outcome"] == "completed"
    saved = json.dumps(service.run_logs(root)) + json.dumps(service.status(root))
    for private in ("person@example.com", "secret-token", "private body"):
        assert private not in saved
    assert type(error).__name__ in result["error"]


def test_backfill_stops_after_healthy_sources_are_empty(mixed_sources, monkeypatch):
    from connectonion.rem.source import Batch
    root, _, _, _ = mixed_sources
    calls = []
    def client(*a):
        calls.append(True)
        if len(calls) > 1:
            pytest.fail("an empty successful source must not retry a failed mailbox forever")
        return FailingMailbox()
    monkeypatch.setattr(service, "mail_client", client)
    monkeypatch.setattr(service, "collect", lambda *a: Batch([], {"offset": 20}))
    result = service.run_sync(root, all_pending=True)
    assert result["batches"] == 1
    record = next(run for run in service.run_logs(root) if run["id"] == result["runs"][0])
    assert record["outcome"] == "completed" and record["failed_source"] == "gmail"
    assert result["outcome"] == "completed" and "gmail" in result["warning"]


def test_failed_mailbox_status_action_keeps_explicit_notebook(mixed_sources, monkeypatch):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    root, _, _, _ = mixed_sources
    monkeypatch.setattr(service, "_quota_status", lambda *a: {})
    service.run_sync(root, runner=lambda *a, **kw: {"changed": []})
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "status"])
    assert result.exit_code == 0, result.output
    assert f"co rem --root {root.resolve()} logs" in result.output
