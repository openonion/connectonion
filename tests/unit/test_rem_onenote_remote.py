"""Selected Graph bodies are refreshed by normal REM, including same-time edits."""
import json
from contextlib import nullcontext

import pytest
import yaml

from connectonion.rem import remote_sources, service
from connectonion.rem.config import prepare
from connectonion.rem.files import read_json, state_path
from connectonion.useful_tools.adapter import resolve_reference
from onenote_source_fixtures import graph


@pytest.fixture
def connected(tmp_path, monkeypatch, graph):
    monkeypatch.setattr(service, "mail_available", lambda _: False)
    monkeypatch.setattr(remote_sources, "credentials", lambda source: nullcontext())
    monkeypatch.setattr(remote_sources, "require_saved", lambda *names: None)
    root = tmp_path / "rem"
    prepare(root)
    for name in ("codex", "claude-code", "gmail", "outlook", "whatsapp"):
        service.toggle_source(root, name, False)
    config = tmp_path / "scope.yaml"
    config.write_text("notebook: nb-fixture\nsection: section-fixture\npages: [page-good]\n")
    remote_sources.connect(root, "onenote", config)
    return root, *graph


def test_metadata_setup_and_dry_run_never_read_html(connected):
    root, routes, calls = connected
    assert not any("/content" in call[1] for call in calls)
    service.run_sync(root, source="onenote", dry_run=True)
    assert not any("/content" in call[1] for call in calls)


def test_initial_and_later_refresh_preserve_mail_scoped_approval(connected, monkeypatch):
    root, _, calls = connected
    monkeypatch.setattr(service, "mail_available", lambda _: True)
    service.toggle_source(root, "gmail", True)
    service.approve_sources(root, mail=("gmail",))
    assert remote_sources.refresh_initial(root, service.subscriptions(root))["onenote"]["complete"]
    assert any("/content" in call[1] for call in calls)
    assert remote_sources.refresh(root, service.subscriptions(root)["onenote"])["complete"]
    from connectonion.rem.config import set_config
    from connectonion.rem.files import RemError
    set_config(root, ["model", "different-model"])
    count = len(calls)
    with pytest.raises(RemError, match="configuration changed"):
        remote_sources.refresh(root, service.subscriptions(root)["onenote"])
    assert len(calls) == count


@pytest.mark.parametrize("local", [False, True])
def test_reader_does_not_project_onenote_credential_location_or_account(connected, local):
    from connectonion.rem.reader import snapshot
    from connectonion.rem.files import write_json
    root = connected[0]
    sources = service.subscriptions(root)
    account = sources["onenote"]["import_identity"]["account"]
    sources["onenote"]["remote"]["credential_file"] = "/synthetic-private/config.env"
    sources["onenote"]["remote"]["credential_home"] = "/synthetic-private/identity"
    write_json(state_path(root, "subscriptions.json"), sources)
    data = json.dumps(snapshot(root, local=local))
    assert account not in data
    assert "/synthetic-private" not in data
    assert "credential_file" not in data
    assert "credential_home" not in data
    assert "account" in service.subscriptions(root)["onenote"]["import_identity"]


def test_same_timestamp_edit_is_automatically_refetched_and_cited(connected):
    root, routes, calls = connected
    service.approve_sources(root)
    items = []
    def runner(notebook, evidence, config, kind=""):
        items.extend(evidence)
        return {}
    assert service.run_sync(root, source="onenote", runner=runner)["items"] == 1
    assert yaml.safe_load((root / "docs/onenote/source.yaml").read_text())["registration"] == "rem_remote"
    old = items[0]["source"].removeprefix("adapter:")
    assert service.run_sync(root, source="onenote", runner=runner)["items"] == 0
    routes["/me/onenote/pages/page-good/content"] = "<html><body>Changed while timestamp stayed fixed</body></html>"
    assert service.run_sync(root, source="onenote", runner=runner)["items"] == 1
    assert "Changed while" in json.loads(items[-1]["text"])["text"]
    assert "Changed while" not in resolve_reference(old, root)["text"]
    assert service.run_sync(root, source="onenote", runner=runner)["items"] == 0
    assert len(items) == 2


def test_model_failure_leaves_full_snapshot_for_retry(connected):
    root, _, _ = connected
    service.approve_sources(root)
    def broken(*args, **kwargs):
        raise RuntimeError("synthetic model failure")
    assert service.run_sync(root, source="onenote", runner=broken)["outcome"] == "failed"
    assert "onenote" not in read_json(state_path(root, "progress.json"), {})
    assert service.run_sync(root, source="onenote", runner=lambda *a, **kw: {})["items"] == 1


def test_denied_body_is_a_failed_read_not_empty_success(connected):
    root, routes, _ = connected
    service.approve_sources(root)
    routes["/me/onenote/pages/page-good/content"] = (403, {"error": "synthetic denied"})
    result = service.run_sync(root, source="onenote", runner=lambda *a, **kw: pytest.fail("model ran"))
    assert result["outcome"] == "failed" and result["source_failures"]
    assert "onenote" not in read_json(state_path(root, "progress.json"), {})


def test_existing_scheduled_dispatch_polls_once_per_due_slot(connected, monkeypatch):
    from datetime import datetime, timezone
    from connectonion.rem.files import write_json
    root = connected[0]
    service.approve_sources(root)
    write_json(state_path(root, "worker.json"), {"enabled": True})
    monkeypatch.setattr(service, "latest_slot", lambda *a: datetime(2026, 11, 6, tzinfo=timezone.utc))
    result = service.run_sync(root, source="onenote", scheduled=True, runner=lambda *a, **kw: {})
    assert result["items"] == 1
    assert service.run_sync(root, source="onenote", scheduled=True, runner=lambda *a, **kw: {}) is None


def test_interactive_scope_selects_listed_page_metadata(monkeypatch):
    from connectonion.rem import onenote_remote, remote_wizard
    from types import SimpleNamespace
    client=SimpleNamespace(verify_connection=lambda:None,
        notebooks=lambda:[{'id':'nb'}],sections=lambda nb:[{'id':'section'}],
        pages=lambda nb,section,limit:{'pages':[{'id':'page'}],'truncated':False})
    monkeypatch.setattr('connectonion.useful_tools.onenote_source.OneNoteSource',lambda:client)
    choices=iter(['nb','section',['page']])
    monkeypatch.setattr(remote_wizard,'pick',lambda *a,**kw:next(choices))
    assert onenote_remote.choose_scope()=={'notebook':'nb','section':'section','pages':['page']}


def test_connect_command_without_scope_file_uses_wizard(connected, monkeypatch):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    root = connected[0]
    chosen = service.subscriptions(root)['onenote']['remote']['selection']
    monkeypatch.setattr('connectonion.rem.remote_wizard.select_scope',lambda kind:chosen)
    result = CliRunner().invoke(app,['rem','--root',str(root),'--json','sources','connect','onenote'])
    assert result.exit_code == 0, result.output
    assert service.subscriptions(root)['onenote']['consented'] is False
