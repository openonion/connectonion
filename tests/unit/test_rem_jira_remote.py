"""Native REM polls the Jira transaction; callers never pre-run a source CLI."""
import copy
import json
from contextlib import nullcontext

import pytest

from connectonion.rem import remote_sources, service
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, read_json, state_path
from connectonion.useful_tools.adapter import resolve_reference


@pytest.fixture
def connected(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "mail_available", lambda _: False)
    monkeypatch.setattr(remote_sources, "credentials", lambda source: nullcontext())
    monkeypatch.setattr(remote_sources, "require_saved", lambda *names: None)
    root = tmp_path / "rem"
    prepare(root)
    for name in ("codex", "claude-code", "gmail", "outlook", "whatsapp"):
        service.toggle_source(root, name, False)
    class Client:
        def __init__(self):
            self.reads = 0
            self.rows = [{"key": "DEMO-1", "fields": {
                "summary": "Synthetic sign-in", "description": "Testing remains pending.",
                "created": "2026-11-01T00:00:00Z", "updated": "2026-11-01T00:00:00Z",
                "status": {"name": "In Progress"},
                "reporter": {"accountId": "person-1", "displayName": "Synthetic Person"}}}]
        def verify_connection(self):
            return {"site_url": "https://jira.example.invalid", "accountId": "account-1"}
        def _get(self, path, **params):
            if path.startswith("issue/"):
                assert params == {"fields": "project"}
                return {"key": path.split("/")[-1], "fields": {"project": {"key": "DEMO"}}}
            return {"key": "DEMO"}
        def scoped_issues(self, project, issue_keys=None, since=None):
            assert project == "DEMO" and issue_keys == ["DEMO-1"]
            self.reads += 1
            return copy.deepcopy(self.rows)
    client = Client()
    monkeypatch.setattr("connectonion.useful_tools.jira.Jira", lambda: client)
    config = tmp_path / "scope.yaml"
    config.write_text("project: DEMO\nissues: [DEMO-1]\nhistory: false\n")
    remote_sources.connect(root, "jira", config)
    return root, client


def test_setup_and_dry_run_never_fetch_issue_bodies(connected):
    root, client = connected
    assert client.reads == 0
    assert not list((root / "docs/jira").glob("daily/*/*/*.jsonl"))
    result = service.run_sync(root, source="jira", dry_run=True)
    assert result["sources"]["jira"]["body_reads"] is False and client.reads == 0


@pytest.mark.parametrize("metadata", [None, {"key": "DEMO-1", "fields": None},
                                    {"key": "DEMO-1", "fields": {"project": None}}])
def test_malformed_selection_metadata_returns_normal_cli_error(connected, tmp_path, metadata):
    from connectonion.cli.main import app
    from typer.testing import CliRunner
    root, client = connected
    client._get = lambda path, **kw: {"key": "DEMO"} if path.startswith("project/") else metadata
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "--json", "sources", "connect",
                                      "jira", "--config", str(tmp_path / "scope.yaml")])
    assert result.exit_code == 1 and json.loads(result.stdout)["ok"] is False
    assert "inaccessible" in result.stdout and client.reads == 0


def test_first_repeat_changed_and_old_citation_via_normal_sync(connected):
    root, client = connected
    service.approve_sources(root)
    items = []
    def runner(notebook, evidence, config, kind=""):
        items.extend(evidence)
        return {}
    assert service.run_sync(root, source="jira", runner=runner)["items"] == 1
    assert Notebook(root).list("projects") and Notebook(root).list("people")
    old = items[0]["source"].removeprefix("adapter:")
    assert service.run_sync(root, source="jira", runner=runner)["items"] == 0
    client.rows[0]["fields"]["status"]["name"] = "Done"
    assert service.run_sync(root, source="jira", runner=runner)["items"] == 1
    assert json.loads(items[-1]["text"])["extensions"]["status"] == "Done"
    assert resolve_reference(old, root)["extensions"]["status"] == "In Progress"
    assert service.run_sync(root, source="jira", runner=runner)["items"] == 0


def test_model_failure_keeps_collected_update_retryable(connected):
    root, client = connected
    service.approve_sources(root)
    def broken(*args, **kwargs):
        raise RuntimeError("synthetic model failure")
    assert service.run_sync(root, source="jira", runner=broken)["outcome"] == "failed"
    assert "jira" not in read_json(state_path(root, "progress.json"), {})
    assert list((root / ".state/jira-cli/checkpoints").glob("*.json"))
    client.rows = []  # server cursor has already advanced; local evidence remains
    assert service.run_sync(root, source="jira", runner=lambda *a, **kw: {})["items"] == 1


def test_new_remote_identity_is_mapped_without_reinitializing(connected):
    root, client = connected
    service.approve_sources(root)
    service.run_sync(root, source="jira", runner=lambda *a, **kw: {})
    client.rows[0]["fields"]["assignee"] = {"accountId": "new-person", "displayName": "Another Synthetic Person"}
    result = service.run_sync(root, source="jira", runner=lambda *a, **kw: {})
    assert result["items"] == 1 and len(Notebook(root).list("people")) == 2


def test_first_missing_selected_issue_is_incomplete_without_checkpoint(connected):
    root, client = connected
    client.rows = []
    service.approve_sources(root)
    result = service.run_sync(root, source="jira", runner=lambda *a, **kw: pytest.fail("model ran"))
    assert result["outcome"] == "failed" and result["source_failures"]
    assert not list((root / ".state/jira-cli/checkpoints").glob("*.json"))


def test_standalone_incremental_respects_same_output_writer_lock(connected):
    from connectonion.rem.files import _file_lock
    from connectonion.useful_tools.jira_checkpoint import run_jira_sync
    root, client = connected
    with _file_lock(root / "docs/jira", 0):
        result = run_jira_sync("DEMO", issue_keys=["DEMO-1"], history=False,
                               output_dir=root / "docs/jira", state_dir=root / ".state/another-cli-state")
    assert result.exit_code == 2 and result.error_code == "lock"
    assert client.reads == 0


def test_partial_first_selection_retains_valid_record_without_advancing_cursor(connected, tmp_path):
    from connectonion.useful_tools.jira_checkpoint import run_jira_sync
    root, client = connected
    state, output = tmp_path / "partial-state", tmp_path / "partial-source"
    client.scoped_issues = lambda *a, **kw: copy.deepcopy(client.rows)
    result = run_jira_sync("DEMO", issue_keys=["DEMO-1", "DEMO-2"], history=False,
                           output_dir=output, state_dir=state, require_selected_first=True)
    assert result.exit_code == 1 and result.net_new_records == 1
    assert "DEMO-2" in result.rejections
    assert list(output.glob("daily/*/*/*.jsonl"))
    assert not list((state / "checkpoints").glob("*.json"))


def test_empty_project_scope_uses_real_client_validation_without_empty_key_filter(tmp_path, monkeypatch):
    from connectonion.useful_tools.jira import Jira
    monkeypatch.setattr(service, "mail_available", lambda _: False)
    monkeypatch.setattr(remote_sources, "credentials", lambda sub: nullcontext())
    monkeypatch.setattr(remote_sources, "require_saved", lambda *names: None)
    monkeypatch.setenv("JIRA_URL", "https://jira.example.invalid")
    monkeypatch.setenv("JIRA_EMAIL", "synthetic@example.invalid")
    monkeypatch.setenv("JIRA_API_TOKEN", "synthetic-test-key")
    monkeypatch.setattr(Jira, "verify_connection", lambda self: {"site_url": "https://jira.example.invalid", "accountId": "id"})
    def get(self, path, **params):
        if path.startswith("project/"):
            return {"key": "DEMO"}
        assert path == "search/jql" and "key IN" not in params["jql"]
        return {"issues": [], "isLast": True}
    monkeypatch.setattr(Jira, "_get", get)
    root = tmp_path / "rem"
    prepare(root)
    for name in ("codex", "claude-code", "gmail", "outlook", "whatsapp"):
        service.toggle_source(root, name, False)
    scope = tmp_path / "scope.yaml"
    scope.write_text("project: DEMO\nhistory: false\n")
    remote_sources.connect(root, "jira", scope)
    service.approve_sources(root)
    result = service.run_sync(root, source="jira", runner=lambda *a, **kw: pytest.fail("model ran"))
    assert result["outcome"] == "no_change" and not result.get("source_failures")


def test_standalone_json_handles_locked_saved_credential_without_leaking_exception(monkeypatch):
    from connectonion.cli.main import app
    from connectonion.secret_store import Undecryptable
    from typer.testing import CliRunner
    def unavailable(name):
        raise Undecryptable("PRIVATE STORE DETAIL")
    monkeypatch.setattr("connectonion.useful_tools.jira.setting", unavailable)
    result = CliRunner().invoke(app, ["jira", "verify", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["source"] == "jira"
    assert "PRIVATE STORE DETAIL" not in result.output


def test_existing_scheduled_dispatch_polls_once_per_due_slot(connected, monkeypatch):
    from datetime import datetime, timezone
    from connectonion.rem.files import write_json
    root = connected[0]
    service.approve_sources(root)
    write_json(state_path(root, "worker.json"), {"enabled": True})
    monkeypatch.setattr(service, "latest_slot", lambda *a: datetime(2026, 11, 6, tzinfo=timezone.utc))
    result = service.run_sync(root, source="jira", scheduled=True, runner=lambda *a, **kw: {})
    assert result["items"] == 1
    assert service.run_sync(root, source="jira", scheduled=True, runner=lambda *a, **kw: {}) is None


def test_interactive_scope_lists_metadata_only(monkeypatch):
    import typer
    from connectonion.rem import jira_remote
    from connectonion.rem import remote_wizard
    from types import SimpleNamespace
    calls=[]
    def get(path, **params):
        calls.append((path,params))
        assert params['fields']=='summary' and 'description' not in params['fields']
        return {'issues':[{'key':'DEMO-1','fields':{'summary':'Synthetic title'}}]}
    client=SimpleNamespace(verify_connection=lambda:None,
        project_items=lambda:[{'key':'DEMO','name':'Demo'}],_get=get)
    monkeypatch.setattr('connectonion.useful_tools.jira.Jira',lambda:client)
    monkeypatch.setattr(typer,'confirm',lambda *a,**kw:False)
    choices=iter(['DEMO',['DEMO-1']])
    monkeypatch.setattr(remote_wizard,'pick',lambda *a,**kw:next(choices))
    assert jira_remote.choose_scope()=={'project':'DEMO','issues':['DEMO-1'],'history':False}
    assert len(calls)==1


def test_connect_command_without_scope_file_uses_wizard(connected, monkeypatch):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    root = connected[0]
    chosen = service.subscriptions(root)['jira']['remote']['selection']
    monkeypatch.setattr('connectonion.rem.remote_wizard.select_scope',lambda kind:chosen)
    result = CliRunner().invoke(app,['rem','--root',str(root),'--json','sources','connect','jira'])
    assert result.exit_code == 0, result.output
    assert service.subscriptions(root)['jira']['consented'] is False


@pytest.mark.parametrize('metadata',[None,{'issues':[{'key':'DEMO-1','fields':None}]}, {'issues':[], 'errors':{'scope':'bad'}}])
def test_wizard_malformed_issue_listing_fails_safely(monkeypatch, metadata):
    import typer
    from types import SimpleNamespace
    from connectonion.rem import jira_remote, remote_wizard
    from connectonion.rem.files import RemError
    client=SimpleNamespace(verify_connection=lambda:None,project_items=lambda:[{'key':'DEMO'}],
                           _get=lambda *a,**kw:metadata)
    monkeypatch.setattr('connectonion.useful_tools.jira.Jira',lambda:client)
    monkeypatch.setattr(remote_wizard,'pick',lambda *a,**kw:'DEMO')
    monkeypatch.setattr(typer,'confirm',lambda *a,**kw:False)
    with pytest.raises(RemError): jira_remote.choose_scope()


def test_wizard_retains_actionable_local_configuration_error(monkeypatch):
    from connectonion.rem import jira_remote
    from connectonion.rem.files import RemError
    from connectonion.useful_tools.jira import JiraConfigError
    def invalid():
        raise JiraConfigError('JIRA_URL must use https:// with a valid host. Repair: co env set JIRA_URL https://your-domain.atlassian.net')
    monkeypatch.setattr('connectonion.useful_tools.jira.Jira',invalid)
    with pytest.raises(RemError,match='co env set JIRA_URL'):
        jira_remote.choose_scope()


def test_real_style_init_with_owner_and_jira_skips_models(connected, monkeypatch, tmp_path):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.rem import runner
    root, client = connected
    monkeypatch.setattr(runner, 'ready', lambda config: ('', ''))
    def no_models(*a, **kw):
        pytest.fail('model work started during map-only initialization')
    monkeypatch.setattr('connectonion.cli.commands.rem_commands._first_pages', no_models)
    monkeypatch.setattr(service, 'run_sync', no_models)
    skills = tmp_path / 'empty-skills'
    skills.mkdir()
    result = CliRunner().invoke(app, ['rem', '--root', str(root), '--json', 'init',
        '--yes', '--no-investigate', '--no-start', '--skills-dir', str(skills),
        '--mine', 'owner@example.invalid', '--name', 'Synthetic Owner'])
    assert result.exit_code == 0, result.output
    assert client.reads == 1
    assert Notebook(root).list('projects') and Notebook(root).list('people')
    receipt = read_json(state_path(root, 'remote_reads.json'), {})['jira']
    assert receipt['complete'] and receipt['written'] == 1
    assert not read_json(state_path(root, 'worker.json'), {}).get('enabled')
