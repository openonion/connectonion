"""Read-only CLI acceptance, written before the Wiki command group."""

import json
import subprocess
import sys

import pytest
import yaml
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
    for name in ("status", "config", "subscriptions", "list", "show", "search", "logs", "doctor"):
        assert name in result.output
    for name in ("approve", "reject", "template", "init"):
        assert name not in result.output.split("Commands")[1]


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
    assert "--help" in result.output


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
    monkeypatch.setattr("connectonion.wiki.runner.run_codex", fake_codex)
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
