"""Unavailable selected sources must not hide healthy, authorized material."""
import pytest

from connectonion.provider_credentials import ProviderCredentialError
from connectonion.rem import service
from connectonion.rem.config import read_config
from connectonion.rem.files import read_json, state_path, write_json
from tests.unit.test_rem_service import rem
from tests.unit.test_rem_source import rollout


def world(rem, monkeypatch, *, error=None, patch_selector=True):
    root, sessions = rem
    rollout(sessions / "rollout-fixture.jsonl", [("user", "Keep the confirmed project decision.")])
    sources = service.subscriptions(root)
    selected = {"gmail": {**sources["gmail"], "enabled": True, "consented": True},
                "codex": sources["codex"]}
    assert selected["codex"]["consented"] and selected["codex"]["since"]
    attempts, received = [], []

    def offline(kind):
        attempts.append(kind)
        raise error or ProviderCredentialError("network_error", "Synthetic authorization service unavailable", "co status")

    def maintain(book, items, config, kind):
        received.append((kind, [i["source"] for i in items]))
        return {"changed": []}

    monkeypatch.setattr(service, "mail_client", offline)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: None)
    if patch_selector:
        monkeypatch.setattr(service, "_selected_sources", lambda *args: selected)
    return root, selected, attempts, received, maintain


@pytest.mark.parametrize("mailbox", ["gmail", "outlook"])
def test_offline_mailbox_does_not_block_available_local_source(rem, monkeypatch, mailbox):
    root, selected, attempts, received, maintain = world(rem, monkeypatch)
    selected[mailbox] = {**selected.pop("gmail"), "kind": mailbox}
    selected = {mailbox: selected[mailbox], "codex": selected["codex"]}
    progress = {mailbox: {"cursor": "preserve-me"}}
    result = service._sync_locked(root, selected, progress, read_config(root), maintain, include_local=False)
    assert received and received[0][0] == "codex", "One unavailable mailbox must not stop healthy selected input"
    assert attempts == [mailbox] and result["outcome"] == "partial"
    assert result["runner_attempts"] == 1 and result["items_by_source"] == {"codex": 1}
    assert result["failed_source"] == mailbox and mailbox in result["warning"]
    saved = read_json(state_path(root, "progress.json"), {})
    assert saved[mailbox] == progress[mailbox] and saved["codex"]
    assert service.run_logs(root)[0]["outcome"] == "partial"


def test_repeated_ticks_do_not_pay_for_healthy_material_again(rem, monkeypatch):
    root, _, attempts, received, maintain = world(rem, monkeypatch)
    assert service.run_sync(root, runner=maintain)["outcome"] == "partial"
    second = service.run_sync(root, runner=maintain)
    assert second["outcome"] == "failed" and second["runner_attempts"] == 0
    assert attempts == ["gmail", "gmail"] and len(received) == 1


def test_all_pending_stops_on_partial_coverage_without_retry_loop(rem, monkeypatch):
    root, _, attempts, received, maintain = world(rem, monkeypatch)
    result = service.run_sync(root, runner=maintain, all_pending=True)
    assert result["outcome"] == "partial" and result["batches"] == 1
    assert attempts == ["gmail"] and len(received) == 1


def test_all_sources_unavailable_remains_failed_without_model(rem, monkeypatch):
    root, selected, attempts, received, maintain = world(rem, monkeypatch, error=OSError("PRIVATE_SECRET"))
    selected.pop("codex")
    selected["outlook"] = {**selected["gmail"], "kind": "outlook"}
    progress = {"gmail": {"cursor": "g"}, "outlook": {"cursor": "o"}}
    write_json(state_path(root, "progress.json"), progress)
    result = service.run_sync(root, runner=maintain, all_pending=True)
    record = service.run_logs(root)[0]
    assert result["outcome"] == "failed" and result["batches"] == 1
    assert attempts == ["gmail", "outlook"] and not received
    assert record["runner_attempts"] == 0 and len(record["source_failures"]) == 2
    assert "PRIVATE_SECRET" not in str(record)
    assert read_json(state_path(root, "progress.json"), {}) == progress


def test_partial_scheduled_slot_is_served_and_status_keeps_source_reason(rem, monkeypatch):
    from zoneinfo import ZoneInfo
    from connectonion.rem.daily import run_daily
    root, _, attempts, received, maintain = world(rem, monkeypatch)
    write_json(state_path(root, "worker.json"), {"enabled": True, "scheduler": "fixture"})
    monkeypatch.setattr(service, "latest_slot", lambda *a: service.now())
    result = run_daily(root, scheduled=True,
                       maintain=lambda root, **kw: service.run_sync(root, runner=maintain, **kw),
                       investigate_one=lambda *a, **kw: pytest.fail("partial coverage must stop investigation"))
    assert result["outcome"] == "partial" and result["investigation"] is None
    assert "authorization service unavailable" in service.worker_state(root)["last_scheduled_reason"]
    assert service.run_sync(root, scheduled=True, runner=maintain) is None
    state, _ = service._state_line(root, read_config(root), ZoneInfo("UTC"))
    assert state.startswith("Background needs attention") and "unavailable" in state
    assert attempts == ["gmail"] and len(received) == 1


def test_disabled_source_is_never_tried_after_failure(rem, monkeypatch):
    root, selected, attempts, received, maintain = world(rem, monkeypatch, patch_selector=False)
    selected["outlook"] = {**selected["gmail"], "kind": "outlook", "enabled": False}
    monkeypatch.setattr(service, "subscriptions", lambda root: selected)
    result = service.run_sync(root, runner=maintain)
    assert result["outcome"] == "partial" and attempts == ["gmail"]
    assert "outlook" not in result["sources"]


def test_available_mailbox_after_failed_mailbox_uses_only_its_own_kind(rem, monkeypatch):
    from connectonion.rem.source import Batch
    root, selected, attempts, received, maintain = world(rem, monkeypatch)
    selected.pop("codex")
    selected["outlook"] = {**selected["gmail"], "kind": "outlook"}
    offline = service.mail_client
    monkeypatch.setattr(service, "mail_client", lambda kind: object() if kind == "outlook" else offline(kind))
    monkeypatch.setattr(service, "collect_mail", lambda *a, **kw: Batch(
        [{"source": "outlook:fixture:1", "text": "Confirmed synthetic decision", "role": "user"}],
        {"cursor": "next"}))
    result = service.run_sync(root, runner=maintain)
    assert result["outcome"] == "partial" and received == [("outlook", ["outlook:fixture:1"])]
    assert result["items_by_source"] == {"outlook": 1} and result["runner_attempts"] == 1
    assert read_json(state_path(root, "progress.json"), {})["outlook"] == {"cursor": "next"}


@pytest.mark.parametrize("as_json", [False, True])
def test_cli_explicit_sync_reports_partial_coverage_as_nonzero(rem, monkeypatch, as_json):
    import json
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    root, _ = rem
    monkeypatch.setattr(service, "run_sync", lambda *a, **kw: {
        "id": "run_fixture", "outcome": "partial", "error": "Synthetic mailbox unavailable"})
    args = ["rem", "--root", str(root), *(["--json"] if as_json else []), "sync", "--source", "codex"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1 and "partial" in result.output and "unavailable" in result.output
    if as_json:
        assert json.loads(result.stdout)["ok"] is False
