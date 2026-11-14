"""Normal REM refreshes approved personal summaries without a manual import."""
import copy
import json
from contextlib import nullcontext
from datetime import timezone

import pytest

from connectonion.rem import remote_sources, service, granola_remote
from connectonion.rem.config import prepare
from connectonion.rem.files import read_json, state_path
from connectonion.useful_tools.adapter import resolve_reference
from connectonion.useful_tools.granola import GranolaClient, GranolaIncompleteRead
from tests.unit.granola_fixtures import NOTE_FULL, FOLDER_ID


@pytest.fixture
def connected(tmp_path, monkeypatch, request):
    monkeypatch.setattr(service, "mail_available", lambda _: False)
    monkeypatch.setattr("connectonion.rem.config.local_timezone", lambda: "UTC")
    monkeypatch.setattr("connectonion.rem.config.ZoneInfo", lambda _: timezone.utc)
    monkeypatch.setattr(service, "ZoneInfo", lambda _: timezone.utc)
    monkeypatch.setattr("connectonion.rem.sessions.ZoneInfo", lambda _: timezone.utc)
    # Keep these source tests independent of the current upstream's
    # POSIX-only SQLite index rebuild (os.O_NOFOLLOW is unavailable on Windows).
    monkeypatch.setattr("connectonion.rem.store.refresh_safely", lambda _: {"fresh": False})
    monkeypatch.setattr("connectonion.rem.people_basics.refresh", lambda _: False)
    monkeypatch.setattr(remote_sources, "credentials", lambda source: nullcontext())
    monkeypatch.setenv("GRANOLA_API_KEY", "synthetic-auto-key")
    monkeypatch.setattr(remote_sources, "require_saved", lambda *names: None)
    root = tmp_path / "rem"
    prepare(root)
    for name in ("codex", "claude-code", "gmail", "outlook", "whatsapp"):
        service.toggle_source(root, name, False)
    class Client:
        write_source_yaml = GranolaClient.write_source_yaml
        def __init__(self):
            self.notes = [copy.deepcopy(NOTE_FULL)]
            self.body_reads = 0
            self.partial = False
        def list_folders(self):
            return [{"id": FOLDER_ID, "space_id": None}]
        def list_notes(self, **kwargs):
            assert kwargs["folder_id"] == FOLDER_ID
            return [{"id": note["id"]} for note in self.notes]
        def hydrate_notes(self, stubs):
            self.body_reads += len(stubs)
            if self.partial:
                raise GranolaIncompleteRead("synthetic failure with PRIVATE TEXT", [self.notes])
            return copy.deepcopy(self.notes)
    client = Client()
    monkeypatch.setattr("connectonion.useful_tools.granola.GranolaClient", lambda: client)
    config = tmp_path / "scope.yaml"
    config.write_text(f"folder_id: {FOLDER_ID}\nprofile: synthetic\nlimit: 2\n"
                      + ("include_children: true\n" if getattr(request, "param", False) else ""))
    remote_sources.connect(root, "granola", config)
    return root, client


def test_connection_and_dry_run_read_no_summary(connected):
    root, client = connected
    assert client.body_reads == 0
    service.run_sync(root, source="granola", dry_run=True)
    assert client.body_reads == 0


def test_native_first_repeat_and_change_keep_old_citations(connected):
    root, client = connected
    service.approve_sources(root)
    items = []
    def runner(notebook, evidence, config, kind=""):
        items.extend(evidence)
        return {}
    assert service.run_sync(root, source="granola", runner=runner)["items"] == 1
    old = items[0]["source"].removeprefix("adapter:")
    assert service.run_sync(root, source="granola", runner=runner)["items"] == 0
    client.notes[0]["title"] = "Changed synthetic summary title"
    assert service.run_sync(root, source="granola", runner=runner)["items"] == 1
    assert resolve_reference(old, root)["title"] != client.notes[0]["title"]
    assert service.run_sync(root, source="granola", runner=runner)["items"] == 0
    assert len(items) == 2


def test_partial_keeps_valid_versions_and_retries_without_false_success(connected):
    root, client = connected
    service.approve_sources(root)
    client.partial = True
    result = service.run_sync(root, source="granola", runner=lambda *a, **kw: pytest.fail("model ran on partial"))
    assert result["outcome"] == "failed" and result["source_failures"]
    assert list((root / "docs/granola").glob("daily/*/*/*.jsonl"))
    assert "PRIVATE" not in str(read_json(state_path(root, "remote_reads.json"), {}))
    assert "granola" not in read_json(state_path(root, "progress.json"), {})
    client.partial = False
    assert service.run_sync(root, source="granola", runner=lambda *a, **kw: {})["items"] == 1


def test_rotated_key_is_rejected_before_any_summary_read(connected, monkeypatch):
    root, client = connected
    service.approve_sources(root)
    monkeypatch.setenv("GRANOLA_API_KEY", "synthetic-other-key")
    assert service.run_sync(root, source="granola", runner=lambda *a, **kw: {})["outcome"] == "failed"
    assert client.body_reads == 0


def test_standalone_import_cannot_reuse_old_binding_with_changed_key(connected, monkeypatch):
    from connectonion.useful_tools.granola import validate_source_identity, GranolaConfigError
    root, client = connected
    monkeypatch.setenv("GRANOLA_API_KEY", "synthetic-other-key")
    with pytest.raises(GranolaConfigError, match="another Granola key"):
        validate_source_identity(root / "docs/granola", FOLDER_ID, "synthetic")
    assert client.body_reads == 0


@pytest.mark.parametrize("folders", [[{"id": FOLDER_ID}],
    [{"id": FOLDER_ID, "space_id": None}, {"id": "child", "space_id": None, "parent_folder_id": FOLDER_ID}]])
def test_unknown_personal_status_or_child_folder_stops_before_note_reads(connected, monkeypatch, folders):
    root, client = connected
    service.approve_sources(root)
    monkeypatch.setattr(client, "list_folders", lambda: folders)
    result = service.run_sync(root, source="granola", runner=lambda *a, **kw: pytest.fail("model ran"))
    assert result["outcome"] == "failed" and client.body_reads == 0


def test_standalone_json_handles_undecryptable_key(monkeypatch):
    import json
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.secret_store import Undecryptable
    def unavailable(name):
        raise Undecryptable("PRIVATE STORE DETAIL")
    monkeypatch.setattr("connectonion.environment.setting", unavailable)
    result = CliRunner().invoke(app, ["granola", "verify", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["source"] == "granola"
    assert "PRIVATE STORE DETAIL" not in result.output


@pytest.mark.parametrize("membership", [None, {"private_notes_text": "PRIVATE"},
                                      [{"id": "folder", "space_id": None, "private_notes_text": "PRIVATE"}]])
def test_client_discards_vendor_private_fields_before_source_collection(monkeypatch, membership):
    from unittest.mock import Mock
    monkeypatch.setenv("GRANOLA_API_KEY", "synthetic-key")
    client = GranolaClient(_http=Mock())
    payload = copy.deepcopy(NOTE_FULL)
    payload.update(private_notes_text="PRIVATE", transcript=[{"text": "PRIVATE"}],
                   attendees=[{"email": "private@example.invalid"}], attachments=[{"url": "PRIVATE"}])
    payload["folder_membership"] = membership
    request = Mock(return_value=payload)
    monkeypatch.setattr(client, "_request", request)
    note = client.get_note(payload["id"])
    assert not {"private_notes_text", "transcript", "attendees", "attachments"} & note.keys()
    assert "PRIVATE" not in json.dumps(note)
    request.assert_called_once_with("/notes/" + payload["id"])


@pytest.mark.parametrize("connected", [True], indirect=True)
def test_explicit_child_scope_accepts_new_personal_descendant_and_preserves_actual_folder(connected, monkeypatch):
    import json
    from connectonion.rem.granola_imports import snapshot_rows
    root, client = connected
    monkeypatch.setattr(client, "list_folders", lambda: [
        {"id": FOLDER_ID, "space_id": None},
        {"id": "child-folder", "space_id": None, "parent_folder_id": FOLDER_ID}])
    client.notes[0]["folder_membership"] = [{"id": "child-folder", "space_id": None, "name": "Synthetic child"}]
    client.notes[0]["folder_id"] = "child-folder"
    service.approve_sources(root)
    captured = []
    def runner(notebook, items, config, kind=""):
        captured.extend(items)
        return {}
    assert service.run_sync(root, source="granola", runner=runner)["items"] == 1
    row = json.loads(captured[0]["text"])
    assert row["extensions"]["folder_id"] == "child-folder"
    assert row["extensions"]["collection_folder_path"] == [FOLDER_ID, "child-folder"]
    assert len(snapshot_rows(root, service.subscriptions(root)["granola"])) == 1
    assert service.run_sync(root, source="granola", runner=runner)["items"] == 0


@pytest.mark.parametrize("connected", [True], indirect=True)
def test_child_opt_in_never_admits_shared_space_descendant(connected, monkeypatch):
    root, client = connected
    monkeypatch.setattr(client, "list_folders", lambda: [
        {"id": FOLDER_ID, "space_id": None},
        {"id": "team-child", "space_id": "shared-space", "parent_folder_id": FOLDER_ID}])
    service.approve_sources(root)
    result = service.run_sync(root, source="granola", runner=lambda *a, **kw: pytest.fail("model ran"))
    assert result["outcome"] == "failed" and client.body_reads == 0


def test_explicit_child_import_uses_same_collector_and_scope_declaration(connected, monkeypatch):
    import json
    import yaml
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.cli.commands import granola_commands
    root, client = connected
    monkeypatch.setattr(client, "list_folders", lambda: [
        {"id": FOLDER_ID, "space_id": None},
        {"id": "child-folder", "space_id": None, "parent_folder_id": FOLDER_ID}])
    client.notes[0]["folder_membership"] = [{"id": "child-folder", "space_id": None}]
    monkeypatch.setattr(granola_commands, "_granola", lambda: client)
    output = root / "separate-manual-output"
    result = CliRunner().invoke(app, ["granola", "import", FOLDER_ID, "--include-children", "--limit", "2",
                                    "--output", str(output), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["appended"] == 1
    assert yaml.safe_load((output / "source.yaml").read_text())["scope"]["include_children"] is True


def test_existing_scheduled_dispatch_polls_once_per_due_slot(connected, monkeypatch):
    from datetime import datetime, timezone
    from connectonion.rem.files import write_json
    root = connected[0]
    service.approve_sources(root)
    write_json(state_path(root, "worker.json"), {"enabled": True})
    monkeypatch.setattr(service, "latest_slot", lambda *a: datetime(2026, 11, 6, tzinfo=timezone.utc))
    result = service.run_sync(root, source="granola", scheduled=True, runner=lambda *a, **kw: {})
    assert result["items"] == 1
    assert service.run_sync(root, source="granola", scheduled=True, runner=lambda *a, **kw: {}) is None


def test_interactive_personal_child_selection_never_fetches_summary(monkeypatch):
    import typer
    from connectonion.rem import granola_remote, remote_wizard
    from types import SimpleNamespace
    folders=[{'id':'root','space_id':None},{'id':'child','space_id':None,'parent_folder_id':'root'},
             {'id':'team','space_id':'shared'}]
    client=SimpleNamespace(list_folders=lambda:folders)
    monkeypatch.setattr('connectonion.useful_tools.granola.GranolaClient',lambda:client)
    def pick(rows,*a,**kw):
        assert [row['id'] for row in rows]==['root','child']
        return 'root'
    monkeypatch.setattr(remote_wizard,'pick',pick)
    answers=iter([True,False])
    monkeypatch.setattr(typer,'confirm',lambda *a,**kw:next(answers))
    monkeypatch.setattr(typer,'prompt',lambda label,**kw:kw['default'])
    assert granola_remote.choose_scope()=={'folder_id':'root','profile':'personal','include_children':True,'limit':1000}


def test_connect_command_without_scope_file_uses_wizard(connected, monkeypatch):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    root = connected[0]
    chosen = service.subscriptions(root)['granola']['remote']['selection']
    monkeypatch.setattr('connectonion.rem.remote_wizard.select_scope',lambda kind:chosen)
    result = CliRunner().invoke(app,['rem','--root',str(root),'--json','sources','connect','granola'])
    assert result.exit_code == 0, result.output
    assert service.subscriptions(root)['granola']['consented'] is False


def test_wizard_partial_metadata_reports_recoverable_error(monkeypatch):
    from types import SimpleNamespace
    from connectonion.rem import granola_remote
    from connectonion.rem.files import RemError
    from connectonion.useful_tools.granola import GranolaIncompleteRead
    def incomplete(): raise GranolaIncompleteRead('PRIVATE details',[])
    monkeypatch.setattr('connectonion.useful_tools.granola.GranolaClient',lambda:SimpleNamespace(list_folders=incomplete))
    with pytest.raises(RemError,match='incomplete') as error: granola_remote.choose_scope()
    assert 'PRIVATE' not in str(error.value)
