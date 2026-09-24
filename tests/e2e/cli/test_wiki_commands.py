"""Read-only CLI acceptance, written before the Wiki command group."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from rich.text import Text
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.wiki.config import default_config, prepare
from connectonion.wiki.files import Notebook

runner = CliRunner()


def invoke(root, *args):
    return runner.invoke(app, ["wiki", "--root", str(root), *args])


@pytest.mark.parametrize("args", [(), ("status",), ("config",), ("subscriptions",),
                                 ("list", "people"), ("logs",), ("search", "Alice")])
def test_inspection_before_start_does_not_create_files(tmp_path, args):
    root = tmp_path / "wiki"
    result = invoke(root, *args)
    assert result.exit_code == 0, result.output
    assert "Next:" in result.output
    assert not root.exists()


def test_help_lists_only_implemented_commands_and_no_fake_start(tmp_path):
    result = invoke(tmp_path, "--help")
    assert result.exit_code == 0
    for name in ("status", "config", "subscriptions", "list", "show", "search", "logs", "doctor", "init", "people", "abstract"):
        assert name in result.output
    for name in ("approve", "reject", "template"):
        assert not __import__("re").search(r"│\s+" + name + r"\s{2,}", result.output.split("Commands")[1])


def test_file_listing_show_and_literal_search(tmp_path):
    prepare(tmp_path)
    Notebook(tmp_path).write("people/alice.md", "# Alice\nWorks on Project Aurora.")
    listing = invoke(tmp_path, "list", "people")
    assert listing.exit_code == 0
    assert "people/alice.md" in listing.output
    assert "show people/alice.md" in listing.output
    shown = invoke(tmp_path, "show", "people/alice.md")
    assert shown.exit_code == 0
    assert "Works on Project Aurora" in shown.output
    matches = invoke(tmp_path, "search", "aurora", "--type", "people")
    assert matches.exit_code == 0
    assert "people/alice.md" in matches.output


def test_json_next_command_preserves_custom_root(tmp_path):
    root = tmp_path / "wiki with spaces"
    result = runner.invoke(app, ["wiki", "--root", str(root), "--json", "status"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["next"].startswith("co wiki --root ")
    assert str(root) in payload["next"]
    assert "Not started" in payload["data"]["state"]


def test_missing_record_is_nonzero_and_names_a_real_recovery_command(tmp_path):
    result = invoke(tmp_path, "show", "people/missing.md")
    assert result.exit_code == 1
    assert "Record not found" in result.output
    assert "list people" in result.output


def test_usage_error_names_help(tmp_path):
    result = invoke(tmp_path, "no-such-command")
    assert result.exit_code == 2
    # Rich can insert style boundaries inside an option in a colored terminal.
    assert "--help" in Text.from_ansi(result.output).plain


def test_read_commands_do_not_invoke_a_provider(tmp_path, monkeypatch):
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: pytest.fail("spawned a provider"))
    for args in [("status",), ("list", "notes"), ("logs",), ("config",)]:
        result = invoke(tmp_path, *args)
        assert result.exit_code == 0, result.output


def test_config_set_is_explicit_and_does_not_prepare_content(tmp_path):
    root = tmp_path / "wiki"
    result = invoke(root, "config", "set", "schedule.timezone", "Australia/Sydney",
                    "model", "gpt-5.6-luna")
    assert result.exit_code == 0, result.output
    assert (root / "config.yaml").is_file()
    assert not (root / "people").exists()
    assert "gpt-5.6-luna" in invoke(root, "config").output


@pytest.mark.parametrize("schedule", [None, {}, {"times": ["17:00"], "timezone": "Not/AZone"}])
def test_malformed_config_has_a_diagnostic_without_rewriting(tmp_path, schedule):
    config = default_config()
    config["schedule"] = schedule
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    original = path.read_bytes()
    for args in [("status",), ("config", "set", "schedule.times", "18:00")]:
        result = invoke(tmp_path, *args)
        assert result.exit_code == 1
        assert "Next:" in result.output
        assert "config" in result.output.lower() or "timezone" in result.output.lower()
        assert path.read_bytes() == original


@pytest.mark.parametrize("json_mode", [False, True])
def test_real_process_piped_output_keeps_next_command(tmp_path, json_mode):
    root = tmp_path / "not initialized"
    command = [sys.executable, "-m", "connectonion.cli.main", "wiki", "--root", str(root)]
    if json_mode:
        command.append("--json")
    result = subprocess.run(command + ["status"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    next_command = json.loads(result.stdout)["next"] if json_mode else result.stdout.split("Next: ")[1].strip()
    assert "co wiki --root " in next_command
    assert str(root) in next_command
    assert next_command.endswith(" logs")
    assert not root.exists()


def test_open_renders_a_local_page_without_touching_the_notebook(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: opened.append(url) or True)
    prepare(tmp_path)
    Notebook(tmp_path).write("people/alice.md", "# Alice\n")
    result = invoke(tmp_path, "open", "--no-launch")
    assert result.exit_code == 0, result.output
    assert opened == []
    assert ".html" in result.output and "Next:" in result.output
    assert Notebook(tmp_path).list() == ["people/alice.md"]
    launched = invoke(tmp_path, "open")
    assert launched.exit_code == 0, launched.output
    assert len(opened) == 1 and opened[0].startswith("file://")


def test_open_uses_owner_wiki_url_when_no_root_is_selected(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    prepare(tmp_path / ".co/wiki")
    monkeypatch.setattr("connectonion.address.load",
                        lambda directory: {"address": "0x" + "a" * 64})
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    result = runner.invoke(app, ["wiki", "open"])
    assert result.exit_code == 0, result.output
    assert opened == [f"https://chat.openonion.ai/0x{'a' * 64}/wiki"]


def test_open_before_start_creates_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: True)
    root = tmp_path / "wiki"
    result = invoke(root, "open")
    assert result.exit_code == 0, result.output
    assert not root.exists()


def test_help_lists_open(tmp_path):
    result = invoke(tmp_path, "--help")
    assert "open" in result.output.split("Commands")[1]


class _CliScheduler:
    installed, uninstalled = [], []

    def install(self, root, config):
        self.installed.append(root)
        return {"scheduler": "fake", "label": "fake", "plist": "/dev/null"}

    def uninstall(self, root):
        self.uninstalled.append(root)
        return True

    def describe(self, root):
        return {"installed": True}


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr("connectonion.wiki.service.codex_sessions_root", lambda: sessions)
    monkeypatch.setattr("connectonion.wiki.schedule.default_scheduler", lambda: _CliScheduler())
    calls = []

    def fake_codex(notebook, items, config):
        calls.append(items)
        return {"usage": None, "changed": []}
    monkeypatch.setattr("connectonion.wiki.runner.run_stage", fake_codex)
    return tmp_path / "wiki", sessions, calls


def test_help_lists_the_lifecycle_commands(tmp_path):
    result = invoke(tmp_path, "--help")
    commands = result.output.split("Commands")[1]
    for name in ("start", "stop", "sync", "subscribe", "unsubscribe"):
        assert name in commands


def test_sync_before_start_is_refused_and_names_start(lifecycle):
    root, sessions, calls = lifecycle
    result = invoke(root, "sync")
    assert result.exit_code == 1
    assert "start" in result.output and calls == []


def test_noninteractive_start_cannot_consent_silently(lifecycle, monkeypatch):
    root, sessions, calls = lifecycle
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    result = invoke(root, "start")
    assert result.exit_code == 1
    assert "--yes" in result.output and str(sessions) in result.output
    assert not (root / ".state" / "consent.json").exists()


def test_start_yes_then_stop(lifecycle):
    root, sessions, calls = lifecycle
    result = invoke(root, "start", "--yes")
    assert result.exit_code == 0, result.output
    assert (root / ".state" / "consent.json").is_file()
    assert _CliScheduler.installed and "status" in result.output.split("Next:")[1]
    stopped = invoke(root, "stop")
    assert stopped.exit_code == 0, stopped.output
    assert _CliScheduler.uninstalled and "start" in stopped.output.split("Next:")[1]


def test_subscribe_and_unsubscribe_round_trip(lifecycle):
    root, sessions, calls = lifecycle
    result = invoke(root, "subscribe", "codex", "--project", str(sessions.parent), "--since", "30d")
    assert result.exit_code == 0, result.output
    listing = invoke(root, "--json", "subscriptions")
    data = json.loads(listing.stdout)["data"]
    custom = [name for name in data if name.startswith("codex-")]
    assert custom and data[custom[0]]["project"] == str(sessions.parent.resolve())
    off = invoke(root, "unsubscribe", "codex")
    assert off.exit_code == 0
    assert json.loads(invoke(root, "--json", "subscriptions").stdout)["data"]["codex"]["enabled"] is False


def test_scheduled_sync_is_quiet_when_no_slot_is_due(lifecycle):
    root, sessions, calls = lifecycle
    assert invoke(root, "start", "--yes").exit_code == 0
    result = invoke(root, "--json", "sync", "--scheduled")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["due"] is False


def test_sync_all_is_the_backfill(lifecycle):
    root, sessions, calls = lifecycle
    assert invoke(root, "start", "--yes").exit_code == 0
    result = invoke(root, "--json", "sync", "--all")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["outcome"] == "caught_up"


def test_usage_command_shows_where_tokens_went(tmp_path):
    from connectonion.wiki.files import state_path, write_json
    prepare(tmp_path)
    runs = state_path(tmp_path, "runs")
    runs.mkdir(parents=True, exist_ok=True)
    write_json(runs / "run_a.json", {"id": "run_a", "started_at": "2026-09-08T01:00:00+00:00", "outcome": "completed",
                                     "model": "gpt-5.6-luna", "items": 10, "chars_in": 5000, "seconds": 20.0,
                                     "usage": {"input_tokens": 1000, "output_tokens": 100},
                                     "usage_by_stage": {"maintain": {"input_tokens": 1000, "output_tokens": 100}},
                                     "items_by_source": {"outlook": 10}})
    result = invoke(tmp_path, "usage")
    assert result.exit_code == 0, result.output
    assert "outlook" in result.output and "maintain" in result.output and "gpt-5.6-luna" in result.output
    assert "Next:" in result.output
    empty = invoke(tmp_path / "nothing", "usage")
    assert empty.exit_code == 0 and "0" in empty.output


@pytest.mark.parametrize("stage", ["abstract"])
def test_skill_entry_points_delegate_and_return_a_next_command(tmp_path, monkeypatch, stage):
    calls = []

    def run(notebook, items, config, **kw):
        calls.append((notebook.root, items, kw["stage"]))
        return {"changed": [], "usage": None, "report": "done"}

    monkeypatch.setattr("connectonion.wiki.runner.run_stage", run)
    result = invoke(tmp_path, "--json", stage)
    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    assert output["ok"] and output["next"].startswith("co wiki")
    assert calls == [(tmp_path, [], stage)]


def test_people_roster_returns_identity_and_existing_path(tmp_path):
    prepare(tmp_path)
    Notebook(tmp_path).stub_person("people/ody.md", "Ody Zhou", ["odi"], email="ody@example.org")
    result = invoke(tmp_path, "--json", "people")
    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    assert "ody@example.org" in str(output["data"])
    assert "people/ody.md" in str(output["data"]) and "odi" in str(output["data"])
    assert output["next"].endswith("list people")


def test_init_builds_all_maps_without_model_or_investigation(tmp_path, monkeypatch):
    monkeypatch.setattr('connectonion.wiki.service.subscriptions', lambda root: {})
    monkeypatch.setattr('connectonion.wiki.runner.run_stage', lambda *a, **kw: pytest.fail('init must not start a model'))
    empty = tmp_path / 'empty-skills'
    empty.mkdir()
    result = invoke(tmp_path, '--json', 'init', '--skills-dir', str(empty))
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)['data']
    assert data['phase'] == 'mapped' and data['investigation'] == 'not started'
    for record in ('notes/people-map.md', 'notes/projects-map.md', 'notes/orgs-map.md', 'skills/catalog/index.md'):
        assert (tmp_path / record).is_file()


def test_init_asks_whether_a_write_only_address_is_the_owner_s_own(tmp_path, monkeypatch):
    """The question is useless without the command that answers it, and the command
    is useless if it forgets the root the user chose (#1635)."""
    monkeypatch.setattr('connectonion.wiki.service.subscriptions', lambda root: {})
    monkeypatch.setattr('connectonion.wiki.map._mail_rows', lambda *a: ([
        {'name': 'openonion ai', 'address': 'aaronplus1996@gmail.com', 'mails': 106, 'sent': 106,
         'received': 0, 'one_way': True, 'first': '2026-06-25', 'last': '2026-09-23', 'boxes': ['gmail']}], set()))
    empty = tmp_path / 'empty-skills'
    empty.mkdir()
    root = tmp_path / 'wiki with spaces'
    result = invoke(root, '--json', 'init', '--skills-dir', str(empty))
    assert result.exit_code == 0, result.output
    asked = json.loads(result.output)['data']['confirm_own_addresses']
    assert len(asked) == 1
    assert '106 sent, none received' in asked[0]
    assert f"--root '{root}' init --mine aaronplus1996@gmail.com" in asked[0]

    plain = invoke(root, 'init', '--skills-dir', str(empty))
    assert plain.exit_code == 0, plain.output
    assert 'aaronplus1996@gmail.com' in Text.from_ansi(plain.output).plain


@pytest.mark.parametrize("state,expected", [
    ("absent", "gmail: not connected; not searched. Connect it with co auth google"),
    ("broken", "gmail: authorized but could not be opened (TimeoutError); not searched. Check access with co auth status"),
    ("unsubscribed", "gmail: unsubscribed by the user; not searched. Restore it with co wiki subscribe gmail"),
])
def test_init_says_which_of_the_four_source_states_a_mailbox_is_in(tmp_path, monkeypatch, state, expected):
    """Never connected, would not open, and switched off each send the user somewhere
    different, and 'not configured or disabled' sent them to the wrong place (#1616)."""
    connected = state != "absent"
    monkeypatch.setattr('connectonion.wiki.service.subscriptions',
                        lambda root: {"gmail": {"id": "gmail", "kind": "gmail",
                                                "unsubscribed": state == "unsubscribed"}})
    monkeypatch.setattr('connectonion.wiki.service.mail_available', lambda kind: connected and kind == "gmail")

    def client(kind, **kw):
        raise TimeoutError("provider detail")
    monkeypatch.setattr('connectonion.wiki.service.mail_client', client)
    empty = tmp_path / 'empty-skills'
    empty.mkdir()
    result = invoke(tmp_path, '--json', 'init', '--skills-dir', str(empty))
    payload = json.loads(result.output)
    coverage = payload['data']['coverage']
    assert expected in coverage
    assert 'provider detail' not in str(payload)          # the provider's own words stay out
    assert not any('not configured or disabled' in line for line in coverage)


def test_wiki_overview_explains_lifecycle_without_initializing(tmp_path):
    root = tmp_path / 'new wiki'
    result = invoke(root)
    assert result.exit_code == 0, result.output
    for text in ('Build the map', 'investigate', 'sync', '--json', '--help'):
        assert text in result.output
    assert result.output.rstrip().endswith(' init')
    assert not root.exists()


@pytest.mark.parametrize('command,message', [
    ('list', 'No pages found'), ('unfinished', 'No unfinished pages'),
    ('logs', 'No runs recorded'), ('review', 'No review candidates'),
    ('people', 'No people mapped'), ('reflections', 'No reflections recorded'),
])
def test_empty_human_results_are_explained(tmp_path, command, message):
    result = invoke(tmp_path, command)
    assert result.exit_code == 0, result.output
    assert message in result.output
    assert '\n[]\n' not in result.output
    assert 'Next:' in result.output


def test_human_status_uses_labels_and_unknown_usage(tmp_path):
    result = invoke(tmp_path, 'status')
    assert result.exit_code == 0, result.output
    assert 'Wiki status' in result.output
    assert 'Input tokens: Unknown' in result.output
    assert '"state":' not in result.output
    assert 'null' not in result.output


def test_unfinished_tip_names_an_existing_page_and_preserves_root(tmp_path):
    import shlex
    root = tmp_path / 'wiki with spaces'
    prepare(root)
    Notebook(root).stub_project('projects/atlas.md', 'Atlas', ['/tmp/atlas'])
    result = invoke(root, 'unfinished')
    assert result.exit_code == 0, result.output
    command = shlex.split(result.output.split('Next: ')[1].strip())
    assert command == ['co', 'wiki', '--root', str(root), 'investigate', 'projects/atlas.md']


def test_default_lists_are_plain_paths_json_remains_machine_readable(tmp_path):
    prepare(tmp_path)
    Notebook(tmp_path).write('notes/sample.md', '# Sample')
    human = invoke(tmp_path, 'list', 'notes')
    assert '\nnotes/sample.md\n' in human.output
    machine = invoke(tmp_path, '--json', 'list', 'notes')
    assert json.loads(machine.stdout)['data'] == ['notes/sample.md']


@pytest.mark.parametrize('kind,rows,tail', [
    ('projects', [{'name': 'Atlas', 'path': '/tmp/atlas project'}], ['stub', 'project', 'Atlas', '--path', '/tmp/atlas project']),
    ('people', [{'name': 'Mira', 'address': 'mira@example.org', 'mails': 4}],
     ['stub', 'person', 'Mira', '--email', 'mira@example.org', '--handle', 'mira@example.org']),
    ('orgs', [{'domain': 'example.org'}], ['stub', 'org', 'example.org', '--domain', 'example.org']),
])
def test_scan_tips_use_observed_values(tmp_path, monkeypatch, kind, rows, tail):
    import shlex
    from types import SimpleNamespace
    monkeypatch.setattr('connectonion.wiki.service.mail_client', lambda *a, **kw: SimpleNamespace(my_addresses=lambda: []))
    monkeypatch.setattr('connectonion.wiki.scan.scan_people', lambda *a, **kw: rows if kind == 'people' else [])
    monkeypatch.setattr('connectonion.wiki.scan.scan_orgs', lambda *a, **kw: rows)
    monkeypatch.setattr('connectonion.wiki.scan.scan_projects', lambda *a, **kw: rows)
    result = invoke(tmp_path, 'scan', kind)
    assert result.exit_code == 0, result.output
    assert shlex.split(result.output.split('Next: ')[1].strip())[4:] == tail


def test_human_formatter_preserves_partial_errors_and_terminal_safety():
    from connectonion.cli.commands.wiki_output import render
    result = render({'outcome': 'partial', 'errors': [{'source': 'gmail', 'error': 'Access denied'}],
                     'usage': {'input_tokens': None}, 'report': '\x1b[31m untrusted'}, 'daily', failed=True)
    assert 'needs attention' in result and 'Access denied' in result
    assert 'Input tokens: Unknown' in result
    assert '\x1b' not in result


def test_investigate_without_arguments_discovers_real_pages_without_a_model(tmp_path, monkeypatch):
    prepare(tmp_path)
    Notebook(tmp_path).stub_person('people/ody-123.md', 'Ody', ['ody@example.org'])
    monkeypatch.setattr('connectonion.wiki.investigate.investigate', lambda *a, **kw: pytest.fail('model called'))
    result = invoke(tmp_path, 'investigate')
    assert result.exit_code == 0, result.output
    assert 'people/ody-123.md' in result.output
    assert result.output.rstrip().endswith('investigate people/ody-123.md')


def test_investigate_empty_notebook_guides_init(tmp_path):
    root = tmp_path / 'absent'
    result = invoke(root, 'investigate')
    assert result.exit_code == 0, result.output
    assert 'No pages available to investigate' in result.output
    assert result.output.rstrip().endswith(' init')
    assert not root.exists()


@pytest.mark.parametrize('selector', ['Ody', 'ody@example.org', 'people/ody-123.md'])
def test_investigate_resolves_observed_name_email_or_path(tmp_path, monkeypatch, selector):
    prepare(tmp_path)
    Notebook(tmp_path).stub_person('people/ody-123.md', 'Ody', ['ody@example.org'], email='ody@example.org')
    monkeypatch.setattr('connectonion.wiki.service.subscriptions', lambda root: {})
    calls = []
    def run(root, record, *args, **kwargs):
        calls.append(record)
        return {'record': record, 'changed': []}
    monkeypatch.setattr('connectonion.wiki.investigate.investigate', run)
    result = invoke(tmp_path, 'investigate', selector)
    assert result.exit_code == 0, result.output
    assert calls == ['people/ody-123.md']
    assert result.output.rstrip().endswith('show people/ody-123.md')


def test_ambiguous_investigation_shows_choices_without_starting(tmp_path, monkeypatch):
    prepare(tmp_path)
    for suffix in ('one', 'two'):
        Notebook(tmp_path).stub_person(f'people/ody-{suffix}.md', 'Ody', [])
    monkeypatch.setattr('connectonion.wiki.investigate.investigate', lambda *a, **kw: pytest.fail('model called'))
    result = invoke(tmp_path, 'investigate', 'Ody')
    assert result.exit_code == 1, result.output
    assert 'More than one page matches' in result.output
    assert 'people/ody-one.md' in result.output and 'people/ody-two.md' in result.output
    assert result.output.rstrip().endswith(' investigate')


def test_help_orders_first_steps_and_exposes_all_commands(tmp_path):
    from typer.main import get_command
    wiki = get_command(app).commands['wiki']
    output = Text.from_ansi(invoke(tmp_path, '--help').output).plain
    assert output.index('1. Map and investigate') < output.index('2. Browse pages') < output.index('3. Update and review')
    for name in wiki.commands:
        assert __import__('re').search(r'│\s+' + __import__('re').escape(name) + r'\s{2,}', output), name
    assert 'set' in invoke(tmp_path, 'config', '--help').output


def test_investigate_help_does_not_run_even_with_page_argument(tmp_path, monkeypatch):
    monkeypatch.setattr('connectonion.wiki.investigate.investigate', lambda *a, **kw: pytest.fail('model called'))
    result = invoke(tmp_path, 'investigate', '--help', 'people/ody.md')
    assert result.exit_code == 0
    assert 'never runs an investigation' in result.output


def test_json_investigate_discovery_and_missing_selection(tmp_path):
    discovered = json.loads(invoke(tmp_path, '--json', 'investigate').stdout)
    assert discovered['ok'] and discovered['data'] == []
    result = invoke(tmp_path, '--json', 'investigate', 'missing')
    failed = json.loads(result.stdout)
    assert result.exit_code == 1 and not failed['ok']
    assert failed['next'].endswith(' investigate')


def test_group_help_is_a_workflow_with_evidence_and_recovery(tmp_path):
    output = Text.from_ansi(invoke(tmp_path, '--help').output).plain
    output = ' '.join(output.split())
    for phrase in ('First run:', 'Choose a page:', 'Check the result:', 'Update later:',
                   'Do not invent page paths', 'partial coverage', 'co wiki investigate',
                   'JSON', '--root'):
        assert phrase in output, phrase
    assert output.index('First run:') < output.index('1. Map and investigate')


@pytest.mark.parametrize('command,phrases', [
    ('init', ('When to use:', 'Expected result:', 'If sources are missing:', 'co auth status')),
    ('investigate', ('When to use:', 'Choose the input:', 'Check the result:', 'More than one match:')),
    ('sync', ('Before running:', 'co wiki sync --dry-run', 'Source access', 'background schedule', 'co wiki logs')),
])
def test_primary_command_help_teaches_the_workflow(tmp_path, command, phrases):
    output = Text.from_ansi(invoke(tmp_path, command, '--help').output).plain
    plain = ' '.join(output.split())
    for phrase in phrases:
        assert phrase in plain, phrase
def test_a_wrapper_can_put_its_own_name_on_every_next_step(tmp_path, monkeypatch):
    """A thin `remi` command that forwards to `co wiki` is only a product if the tips
    agree with it: a user who typed `remi status` and is told `co wiki --root /long/path
    logs` has been handed the wiring. The wrapper names itself in the environment and
    every Next line follows; the root is omitted when it is the default one."""
    monkeypatch.setenv("CO_WIKI_PROGRAM", "remi")
    result = runner.invoke(app, ["wiki", "--root", str(tmp_path), "status"])
    assert result.exit_code == 0, result.output
    assert result.output.strip().endswith(f"Next: remi --root {tmp_path} logs")
    from pathlib import Path
    default_root = Path.home() / ".co" / "wiki"   # the harness already isolates HOME per test
    result = runner.invoke(app, ["wiki", "--root", str(default_root), "status"])
    assert result.output.strip().endswith("Next: remi logs")  # the default root is not spelled out


def test_subscribing_a_whatsapp_chat_points_at_start(tmp_path):
    """Naming a chat is not permission to read it; the next command is the one
    that shows the user what will be read and asks."""
    result = invoke(tmp_path, '--json', 'subscribe', 'whatsapp', '--chat', '120363411567190840@g.us')
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload['data']['chats'] == ['120363411567190840@g.us']
    assert payload['next'].endswith(' start')
    refused = invoke(tmp_path / 'fresh', 'subscribe', 'whatsapp')   # no chat named yet
    assert refused.exit_code == 1 and 'co whatsapp chats' in refused.output
