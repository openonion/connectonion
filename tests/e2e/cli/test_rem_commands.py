"""Read-only CLI acceptance, written before co rem command group."""

import importlib
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

import httpx
import pytest
import yaml
from rich.text import Text
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook

runner = CliRunner()


def invoke(root, *args):
    return runner.invoke(app, ["rem", "--root", str(root), *args])


@pytest.mark.parametrize("args", [(), ("status",), ("config",), ("subscriptions",),
                                 ("list", "people"), ("logs",), ("search", "Alice")])
def test_inspection_before_start_does_not_create_files(tmp_path, args):
    root = tmp_path / "rem"
    result = invoke(root, *args)
    assert result.exit_code == 0, result.output
    assert "Next:" in result.output
    assert not root.exists()


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


def test_addresses_held_for_review_are_listed_only_when_asked_for(tmp_path):
    """#1844: a nameless address the owner never wrote to stays off the list until promoted."""
    from connectonion.rem.files import state_path, write_json
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/alice.md", "Alice")
    notebook.stub_person("people/x7.md", "x7@shop.example", ["x7@shop.example"])
    write_json(state_path(tmp_path, "map.json"), {"people": [{"record": "people/alice.md"},
                                                             {"record": "people/x7.md", "needs_review": True}]})
    listing = invoke(tmp_path, "--json", "list", "people")
    assert json.loads(listing.output)["data"] == ["people/alice.md"]
    assert json.loads(invoke(tmp_path, "--json", "list").output)["data"]["people"] == 1
    held = invoke(tmp_path, "--json", "list", "people", "--review")
    assert json.loads(held.output)["data"] == ["people/x7.md"]
    assert invoke(tmp_path, "list", "projects", "--review").exit_code != 0


def test_list_people_puts_the_most_mailed_first_not_the_first_file_name(tmp_path):
    """#1670: sorted by file name, an agent's 0x… mailbox came before colleagues."""
    from connectonion.rem.files import state_path, write_json

    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    for record in ("people/0x3c3ae74550.md", "people/alice.md", "people/zoe.md"):
        notebook.write(record, "# " + record)
    write_json(state_path(tmp_path, "map.json"), {"people": [
        {"record": "people/0x3c3ae74550.md", "mails": 2},
        {"record": "people/zoe.md", "mails": 180},
        {"record": "people/alice.md", "mails": 40}]})

    listing = invoke(tmp_path, "--json", "list", "people")

    assert json.loads(listing.stdout)["data"] == ["people/zoe.md", "people/alice.md", "people/0x3c3ae74550.md"]


def test_json_next_command_preserves_custom_root(tmp_path):
    root = tmp_path / "co rem with spaces"
    result = runner.invoke(app, ["rem", "--root", str(root), "--json", "status"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["next"].startswith("co rem --root ")
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
    root = tmp_path / "rem"
    result = invoke(root, "config", "set", "schedule.timezone", "Australia/Sydney",
                    "model", "gpt-5.6-luna", "--no-check")
    assert result.exit_code == 0, result.output
    assert (root / "config.yaml").is_file()
    assert not (root / "people").exists()
    assert "gpt-5.6-luna" in invoke(root, "config").output


def test_config_set_model_checks_it_on_a_fixture_page_and_records_its_tier(tmp_path, monkeypatch):
    """#1847: the tier comes from what the model did, not from its name."""
    def plain_model(workspace, prompt, config, stage):   # can reply, cannot drive tools
        page = re.search(r"^# Ada Fixture$.*?^Investigation:[^\n]*$", prompt, re.M | re.S).group(0)
        source = re.search(r"gmail:[0-9a-f]{12}", prompt).group(0)
        return {"outcome": "natural", "usage": None, "result": page.replace(
            "## Who they are\n- Unknown — not investigated yet",
            "## Who they are\n- Head of research at Lovelace Instruments. [1]").replace(
            "- (none yet)", f"- [1] {source}")}

    monkeypatch.setattr("connectonion.rem.runner.run_task", plain_model)
    root = tmp_path / "rem"
    result = invoke(root, "config", "set", "model", "gpt-7-nova")
    assert result.exit_code == 0, result.output
    assert "Tier: summary" in result.stdout
    recorded = json.loads((root / ".state/tier.json").read_text())
    assert (recorded["tier"], recorded["model"]) == ("summary", "gpt-7-nova")
    assert not (root / "people").exists()
    shown = invoke(root, "config").output
    assert "In force: summary" in shown and shown.rstrip().endswith(f"Next: co rem --root {root} status")
    invoke(root, "config", "set", "model", "gpt-7-pico", "--no-check")
    shown = invoke(root, "config").output
    assert "last checked for codex gpt-7-nova" in shown
    # The check is named in the tier's note; Next no longer reads as "set the model" (#1974).
    assert f"co rem --root {root} config set model gpt-7-pico (one or two model calls)" in shown
    assert shown.rstrip().endswith(f"Next: co rem --root {root} status")


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
    command = [sys.executable, "-m", "connectonion.cli.main", "rem", "--root", str(root)]
    if json_mode:
        command.append("--json")
    result = subprocess.run(command + ["status"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    next_command = json.loads(result.stdout)["next"] if json_mode else result.stdout.split("Next: ")[1].strip()
    assert "co rem --root " in next_command
    assert str(root) in next_command
    assert next_command.endswith(" init")  # nothing built yet: the step status names
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


OWNER = "0x" + "a" * 64


def _owner_notebook(tmp_path, monkeypatch, *, host):
    """The default ~/.co/rem under a tmp home, an identity, and a Host that is
    offline (None), answers directly ("direct"), or is reachable only through the
    relay ("relay": behind NAT, on another machine). The relay's HTTP answer is
    faked at the transport and direct resolution at resolve_endpoint, so the real
    presence check runs on the record shape production sends."""
    from datetime import datetime, timezone
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    root = tmp_path / ".co/rem"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice\nWorks on Project Aurora.")
    monkeypatch.setattr("connectonion.address.load", lambda directory: {"address": OWNER})
    asked = []
    # By module object: connectonion.network re-exports a `connect` function
    # that shadows the module in a dotted-string lookup.
    connect = importlib.import_module("connectonion.network.connect")

    def relay_api(request):
        asked.append(request.url.path.rsplit("/", 1)[-1])
        held = host == "relay"
        return httpx.Response(200, json={
            "endpoints": ["http://10.0.0.5:8000", "ws://10.0.0.5:8000/ws"],
            "relay": "wss://oo.openonion.ai" if held else None,
            "last_seen": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() if held else None,
            "profile": None})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(connect.httpx, "AsyncClient",
                        lambda **kw: real_client(**kw, transport=httpx.MockTransport(relay_api)))

    async def resolve(address, relay_url, timeout=3.0):
        return "ws://127.0.0.1:8000/ws" if host == "direct" else None
    monkeypatch.setattr(connect, "resolve_endpoint", resolve)
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: opened.append(url) or True)
    return root, asked, opened


def _plain(text):
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_default_open_is_a_snapshot_that_exists_and_renders_the_pages(tmp_path, monkeypatch):
    """#1828: the default opened chat.openonion.ai/<address>/wiki, a route O Chat
    does not serve, for a Host nobody had started. The default is the snapshot,
    which loads offline, and it asks no Host anything."""
    _, asked, opened = _owner_notebook(tmp_path, monkeypatch, host=None)
    result = runner.invoke(app, ["rem", "open", "--no-launch"])
    assert result.exit_code == 0, result.output
    output = _plain(result.output)
    link = re.search(r"^Link: (file://\S+)$", output, re.M).group(1)
    snapshot = Path(urllib.parse.unquote(urllib.parse.urlparse(link).path))
    assert snapshot.is_file() and "Works on Project Aurora" in snapshot.read_text(encoding="utf-8")
    assert "co rem open --live" in output
    assert opened == [] and asked == []
    # Rendered on every run, so the page opened is never older than the notebook.
    Notebook(tmp_path / ".co/rem").write("people/bob.md", "# Bob\nJoined yesterday.")
    assert runner.invoke(app, ["rem", "open", "--no-launch"]).exit_code == 0
    assert "Joined yesterday" in snapshot.read_text(encoding="utf-8")


def test_default_open_never_prints_a_chat_openonion_route(tmp_path, monkeypatch):
    """Opening locally is the default (owner's decision on #1828): even with the
    Host online and O Chat serving the route, a bare `co rem open` opens the
    snapshot, which loads offline too."""
    from connectonion.rem import reader
    assert reader.LIVE_IS_DEFAULT is False, "the owner chose local by default (#1828)"
    _, _, opened = _owner_notebook(tmp_path, monkeypatch, host="direct")
    result = runner.invoke(app, ["rem", "--json", "open"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert "chat.openonion.ai" not in data["link"] and data["link"].startswith("file://")
    assert opened == [data["link"]]


def test_live_with_the_host_offline_falls_back_to_the_snapshot_and_names_co_ai(tmp_path, monkeypatch):
    _, asked, opened = _owner_notebook(tmp_path, monkeypatch, host=None)
    result = runner.invoke(app, ["rem", "open", "--live"])
    assert result.exit_code == 0, result.output
    output = _plain(result.output)
    assert asked == [OWNER]
    assert "not online" in output and "co ai" in output
    assert len(opened) == 1 and opened[0].startswith("file://")
    assert "chat.openonion.ai" not in opened[0]


def test_live_with_the_host_online_opens_the_live_url(tmp_path, monkeypatch):
    _, asked, opened = _owner_notebook(tmp_path, monkeypatch, host="direct")
    result = runner.invoke(app, ["rem", "open", "--live", "--no-launch"])
    assert result.exit_code == 0, result.output
    assert asked == [OWNER] and opened == []
    assert f"https://chat.openonion.ai/{OWNER}/wiki" in _plain(result.output)


def test_live_with_the_host_reachable_only_through_the_relay_opens_the_live_url(tmp_path, monkeypatch):
    """A Host behind NAT or on another machine has no endpoint this machine can
    reach, but O Chat reaches it through the relay, so it is online."""
    _, asked, opened = _owner_notebook(tmp_path, monkeypatch, host="relay")
    result = runner.invoke(app, ["rem", "open", "--live", "--no-launch"])
    assert result.exit_code == 0, result.output
    assert asked == [OWNER] and opened == []
    assert f"https://chat.openonion.ai/{OWNER}/wiki" in _plain(result.output)


def test_live_on_a_custom_root_says_why_and_opens_the_snapshot(tmp_path, monkeypatch):
    """The live view reads the default notebook through the co ai identity (#1637);
    a custom --root is not assumed to belong to it."""
    _, asked, _ = _owner_notebook(tmp_path, monkeypatch, host="direct")
    root = tmp_path / "other"
    prepare(root)
    result = invoke(root, "open", "--live", "--no-launch")
    assert result.exit_code == 0, result.output
    assert asked == [] and "file://" in _plain(result.output)


def test_open_before_start_creates_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: True)
    root = tmp_path / "rem"
    result = invoke(root, "open")
    assert result.exit_code == 0, result.output
    assert not root.exists()


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
    monkeypatch.setattr("connectonion.rem.service.codex_sessions_root", lambda: sessions)
    monkeypatch.setattr("connectonion.rem.schedule.default_scheduler", lambda: _CliScheduler())
    calls = []

    def fake_codex(notebook, items, config):
        calls.append(items)
        return {"usage": None, "changed": []}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", fake_codex)
    return tmp_path / "rem", sessions, calls


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


def _spend_the_day(root):
    """A run record that used the whole day's cap, as a busy real day leaves."""
    import uuid
    from datetime import datetime, timezone

    from connectonion.rem.files import state_path, write_json
    record_id = "run_" + uuid.uuid4().hex
    write_json(state_path(root, f"runs/{record_id}.json"),
               {"id": record_id, "started_at": datetime.now(timezone.utc).isoformat(),
                "runner_attempts": 30, "outcome": "completed", "items": 1})


def test_a_sync_refused_by_the_cap_is_in_logs_and_says_when_it_resets(lifecycle):
    """#1957: "Next: co rem logs" pointed at a listing with nothing in it."""
    from tests.unit.test_rem_source import rollout
    root, sessions, calls = lifecycle
    assert invoke(root, "start", "--yes").exit_code == 0
    _spend_the_day(root)
    rollout(sessions / "rollout-a.jsonl", [("user", "one more thing")])
    refused = invoke(root, "sync")
    assert refused.exit_code == 1 and calls == []
    assert "resets" in refused.output and "limits.runner_calls_per_day" in refused.output
    assert refused.output.rstrip().endswith(" config")   # Next names where the cap is set
    logs = json.loads(invoke(root, "--json", "logs").stdout)["data"]
    assert logs[0]["outcome"] == "refused"
    dry = json.loads(invoke(root, "--json", "sync", "--dry-run").stdout)["data"]
    assert dry["daily_cap"]["remaining"] == 0 and dry["daily_cap"]["resets_at"]


def _recording_runner(monkeypatch, calls, stop_after=None):
    """The maintainer as sync calls it, one call per batch; no model."""
    def run_stage(notebook, items, config, **options):
        if stop_after is not None and len(calls) >= stop_after:
            raise KeyboardInterrupt
        calls.append(items)
        return {"usage": None, "changed": []}
    monkeypatch.setattr("connectonion.rem.runner.run_stage", run_stage)


def test_sync_all_reports_each_batch_and_stops_at_the_cap(lifecycle, monkeypatch):
    from connectonion.rem.config import set_config
    from tests.unit.test_rem_source import rollout
    root, sessions, calls = lifecycle
    _recording_runner(monkeypatch, calls)
    assert invoke(root, "start", "--yes").exit_code == 0
    set_config(root, ["limits.items_per_batch", "2", "limits.extract_items_per_batch", "2",
                      "limits.runner_calls_per_day", "2"])
    rollout(sessions / "rollout-a.jsonl", [("user", f"fact {n}") for n in range(7)])
    result = invoke(root, "sync", "--all")
    assert len(calls) == 2 and result.exit_code == 1
    assert "Batch 1:" in result.stderr and "Batch 2:" in result.stderr
    assert "2 batches" in result.output and "resets" in result.output


def test_ctrl_c_during_sync_all_says_what_finished(lifecycle, monkeypatch):
    from connectonion.rem.config import set_config
    from tests.unit.test_rem_source import rollout
    root, sessions, calls = lifecycle
    assert invoke(root, "start", "--yes").exit_code == 0
    set_config(root, ["limits.items_per_batch", "2", "limits.extract_items_per_batch", "2"])
    rollout(sessions / "rollout-a.jsonl", [("user", f"fact {n}") for n in range(7)])
    _recording_runner(monkeypatch, calls, stop_after=1)
    result = invoke(root, "sync", "--all")
    assert result.exit_code == 130
    assert "1 batch finished" in result.stderr


def test_usage_command_shows_where_tokens_went(tmp_path):
    from connectonion.rem.files import state_path, write_json
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

    monkeypatch.setattr("connectonion.rem.runner.run_stage", run)
    result = invoke(tmp_path, "--json", stage)
    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    assert output["ok"] and output["next"].startswith("co rem")
    assert calls == [(tmp_path, [], stage)]


def test_people_roster_returns_identity_and_existing_path(tmp_path):
    prepare(tmp_path)
    Notebook(tmp_path).stub_person("people/ody.md", "Ody Zhou", ["odi"], email="ody@example.org")
    result = invoke(tmp_path, "--json", "list", "people", "--aliases")
    assert result.exit_code == 0, result.output
    output = json.loads(result.stdout)
    assert "ody@example.org" in str(output["data"])
    assert "people/ody.md" in str(output["data"]) and "odi" in str(output["data"])
    assert output["next"].endswith("show people/ody.md")


def test_init_builds_all_maps_without_model_or_investigation(tmp_path, monkeypatch):
    monkeypatch.setattr('connectonion.rem.service.subscriptions', lambda root: {})
    monkeypatch.setattr('connectonion.rem.runner.run_stage', lambda *a, **kw: pytest.fail('init must not start a model'))
    empty = tmp_path / 'empty-skills'
    empty.mkdir()
    result = invoke(tmp_path, '--json', 'init', '--skills-dir', str(empty))
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)['data']
    assert data['phase'] == 'mapped' and data['investigation'] == 'not started'
    for record in ('notes/people-map.md', 'notes/projects-map.md', 'notes/orgs-map.md', 'skills/catalog/index.md'):
        assert (tmp_path / record).is_file()
    assert (tmp_path / '.state/source-inventory.md').is_file()
    assert (tmp_path / '.state/source-inventory.jsonl').is_file()
    plain = invoke(tmp_path, 'init', '--skills-dir', str(empty))
    assert plain.exit_code == 0, plain.output
    # One finished line per stage (#1943), not every step.
    assert 'co rem init: mapped installed skills: 0' in plain.output
    assert 'co rem init: mapped projects: 0' in plain.output


def test_init_archives_connected_mail_body_for_later_investigation(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr('connectonion.rem.service.subscriptions', lambda root: {})
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: kind == 'gmail')
    when = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    class Mail:
        def my_addresses(self): return {'me@example.org'}
        def list_between(self, start, end, limit):
            return ([{'id': 'm1', 'date': when, 'from': 'alice@example.org',
                      'to': ['me@example.org'], 'subject': 'Decision'}]
                    if start <= when < end else [])
        def get_email_body(self, message_id): return '--- Email Body ---\nThe decision'

    monkeypatch.setattr('connectonion.rem.service.mail_client', lambda kind: Mail())
    skills = tmp_path / 'empty-skills'
    skills.mkdir()
    result = invoke(tmp_path, '--json', 'init', '--days', '1', '--skills-dir', str(skills))
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)['data']
    assert data['mail_archive']['phase'] == 'complete'
    assert data['mail_archive']['saved'] == 1
    assert len(list((tmp_path / '.state/mail/messages/gmail').glob('*.json'))) == 1
    person = next(row['record'] for row in data['people'] if row.get('address') == 'alice@example.org')
    assert 'The decision' not in (tmp_path / person).read_text()

    skipped = tmp_path / 'skipped'
    result = invoke(skipped, '--json', 'init', '--days', '1', '--skills-dir', str(skills), '--no-mail-archive')
    assert result.exit_code == 0, result.output
    assert not (skipped / '.state/mail/archive.json').exists()

    previous = (tmp_path / '.state/mail/archive.json').read_bytes()
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    disconnected = invoke(tmp_path, '--json', 'init', '--days', '1', '--skills-dir', str(skills))
    assert disconnected.exit_code == 0, disconnected.output
    assert json.loads(disconnected.stdout)['data']['mail_archive']['phase'] == 'previous_preserved'
    assert (tmp_path / '.state/mail/archive.json').read_bytes() == previous


def test_init_reports_failed_body_without_claiming_complete_archive(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr('connectonion.rem.service.subscriptions', lambda root: {})
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: kind == 'gmail')
    when = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    class Mail:
        def my_addresses(self): return {'me@example.org'}
        def list_between(self, start, end, limit):
            return ([{'id': 'm1', 'date': when, 'from': 'alice@example.org',
                      'to': ['me@example.org'], 'subject': 'Decision'}]
                    if start <= when < end else [])
        def get_email_body(self, message_id): raise TimeoutError('temporary')

    monkeypatch.setattr('connectonion.rem.service.mail_client', lambda kind: Mail())
    skills = tmp_path / 'empty-skills'
    skills.mkdir()
    result = invoke(tmp_path, '--json', 'init', '--days', '1', '--skills-dir', str(skills))
    assert result.exit_code == 1
    data = json.loads(result.stdout)['data']
    assert data['phase'] == 'partial'
    assert data['mail_archive']['phase'] == 'partial'
    assert data['mail_archive']['failed'] == 1
    assert (tmp_path / '.state/mail/archive.json').exists()
    assert any(row['source'] == 'mail-archive' for row in data['errors'])


def test_init_human_output_summarizes_map_instead_of_dumping_contacts():
    from connectonion.cli.commands.rem_output import render

    report = {'phase': 'mapped', 'days': 5, 'people': [{'address': f'user{i}@example.org'}
              for i in range(500)], 'orgs': [{}] * 10, 'projects': [{}] * 3,
              'skills': {'skills': [{'name': f'Skill {i % 2}'} for i in range(400)],
                         'created': ['one', 'two']},
              'created': ['three'], 'investigation': 'not started'}
    text = render(report, 'init')
    assert 'People: 500' in text and 'Projects: 3' in text
    assert 'Skills: 2 names (400 installed copies)' in text and 'New pages: 3' in text
    assert 'user0@example.org' not in text
    assert len(text.splitlines()) < 20


def test_init_asks_whether_a_write_only_address_is_the_owner_s_own(tmp_path, monkeypatch):
    """The question is useless without the command that answers it, and the command
    is useless if it forgets the root the user chose (#1635)."""
    monkeypatch.setattr('connectonion.rem.service.subscriptions', lambda root: {})
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: ([
        {'name': 'openonion ai', 'address': 'aaronplus1996@gmail.com', 'mails': 106, 'sent': 106,
         'received': 0, 'one_way': True, 'first': '2026-06-25', 'last': '2026-09-23', 'boxes': ['gmail']}], set()))
    empty = tmp_path / 'empty-skills'
    empty.mkdir()
    root = tmp_path / 'co rem with spaces'
    result = invoke(root, '--json', 'init', '--skills-dir', str(empty))
    assert result.exit_code == 0, result.output
    asked = json.loads(result.output)['data']['confirm_own_addresses']
    assert len(asked) == 1
    assert '106 sent, none received' in asked[0]
    assert f"--root '{root}' init --mine aaronplus1996@gmail.com" in asked[0]

    plain = invoke(root, 'init', '--skills-dir', str(empty))
    assert plain.exit_code == 0, plain.output
    assert 'co rem init: mapped installed skills' in plain.output
    assert 'co rem init: mapped projects' in plain.output
    assert 'aaronplus1996@gmail.com' in Text.from_ansi(plain.output).plain


def test_init_says_how_many_addresses_are_held_for_review_and_where_to_see_them(tmp_path, monkeypatch):
    monkeypatch.setattr('connectonion.rem.service.subscriptions', lambda root: {})
    monkeypatch.setattr('connectonion.rem.map._mail_rows', lambda *a, **kw: ([
        {'name': '', 'address': 'x7@shop.example', 'mails': 5, 'sent': 0, 'received': 5, 'one_way': True}], set()))
    empty = tmp_path / 'empty-skills'
    empty.mkdir()
    root = tmp_path / 'rem'
    result = invoke(root, 'init', '--skills-dir', str(empty))
    assert result.exit_code == 0, result.output
    assert "Held for review, not investigated or listed (no name, never written to): 1." in result.output
    assert f"--root {root} list people --review" in result.output


@pytest.mark.parametrize("state,expected", [
    ("absent", "gmail: not connected; not searched. Connect it with co auth google"),
    ("broken", "gmail: authorized but could not be opened (TimeoutError); not searched. Check access with co auth status"),
    ("unsubscribed", "gmail: unsubscribed by the user; not searched. Restore it with co rem subscribe gmail"),
])
def test_init_says_which_of_the_four_source_states_a_mailbox_is_in(tmp_path, monkeypatch, state, expected):
    """Never connected, would not open, and switched off each send the user somewhere
    different, and 'not configured or disabled' sent them to the wrong place (#1616)."""
    connected = state != "absent"
    monkeypatch.setattr('connectonion.rem.service.subscriptions',
                        lambda root: {"gmail": {"id": "gmail", "kind": "gmail",
                                                "unsubscribed": state == "unsubscribed"}})
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: connected and kind == "gmail")

    def client(kind, **kw):
        raise TimeoutError("provider detail")
    monkeypatch.setattr('connectonion.rem.service.mail_client', client)
    empty = tmp_path / 'empty-skills'
    empty.mkdir()
    result = invoke(tmp_path, '--json', 'init', '--skills-dir', str(empty))
    payload = json.loads(result.output)
    coverage = payload['data']['coverage']
    assert expected in coverage
    assert 'provider detail' not in str(payload)          # the provider's own words stay out
    assert not any('not configured or disabled' in line for line in coverage)


def test_rem_overview_explains_lifecycle_without_initializing(tmp_path):
    root = tmp_path / 'new co rem'
    result = invoke(root)
    assert result.exit_code == 0, result.output
    for text in ('Build the notebook from', 'investigate', 'sync', '--json', '--help'):
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


def _notebook_with_a_run(root, monkeypatch):
    """Two people (one written), three skills, gmail read by the round, one investigation today."""
    from connectonion.rem.files import state_path, write_json
    from connectonion.rem.service import now
    prepare(root)
    notebook = Notebook(root)
    notebook.stub_person('people/alice.md', 'Alice', ['alice@example.org'])
    notebook.stub_person('people/bob.md', 'Bob', ['bob@example.org'])
    notebook.note_investigation('people/alice.md', 'gmail')
    for name in ('deploy', 'blog', 'triage'):
        notebook.stub_skill(f'skills/catalog/{name}.md', name, f'/skills/{name}/SKILL.md')
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: kind == 'gmail')
    write_json(state_path(root, 'subscriptions.json'), {'gmail': {'id': 'gmail', 'kind': 'gmail', 'enabled': True,
                                                                  'consented': True, 'adapter': 'available'}})
    write_json(state_path(root, 'runs/run_' + 'a' * 32 + '.json'), {
        'id': 'run_' + 'a' * 32, 'started_at': now().isoformat(), 'phase': 'investigate',
        'record': 'people/alice.md', 'outcome': 'completed', 'changed': ['people/alice.md'],
        'runner_attempts': 0, 'usage': {'input_tokens': 91234, 'output_tokens': 812}, 'items': 3})


def test_status_is_a_dashboard_of_the_notebook_not_a_dump_of_fields(tmp_path, monkeypatch):
    """#1996: one header line, the notebook with skills, today, mailboxes with fixes, the last run in one line."""
    _notebook_with_a_run(tmp_path, monkeypatch)
    lines = invoke(tmp_path, 'status').output.splitlines()
    assert lines[0].startswith('co rem status · not started') and 'co rem start' in lines[0]
    assert '  People         1 written of 2 mapped' in lines
    assert '  Skills         0 written of 3 mapped' in lines
    assert any(line.startswith('  To write next  1 people page not written: co rem --root') for line in lines)
    # A manual run records no runner attempts, and its tokens count all the same (#2008).
    assert '  1 run · 1 page changed · 91,234 tokens in, 812 out' in lines
    assert '  ✓ Gmail    read by the daily round' in lines
    assert '  ✗ Outlook  not connected — co auth microsoft' in lines
    last = [line for line in lines if line.startswith('Last run')]
    assert len(last) == 1 and 'investigate people/alice.md · completed · 1 page changed · 91,234 tokens in' in last[0]
    assert lines[-1] == f'Next: co rem --root {tmp_path} investigate people'  # the first thing to write (#2008)
    for internal in ('Known attempts', 'Schedule times', 'Worker', 'Runner attempts today', 'Usage by stage'):
        assert internal not in '\n'.join(lines), internal


def test_status_verbose_adds_the_internal_fields_and_json_keeps_its_keys(tmp_path, monkeypatch):
    _notebook_with_a_run(tmp_path, monkeypatch)
    verbose = invoke(tmp_path, 'status', '--verbose').output
    assert 'Details' in verbose and 'Known runs: 1' in verbose and 'Schedule times:' in verbose
    assert 'Record: people/alice.md' in verbose
    data = json.loads(invoke(tmp_path, '--json', 'status').output)
    assert set(data) == {'ok', 'data', 'next'} and data['next'].endswith(' investigate people')
    assert set(data['data']) == {'state', 'root', 'configured', 'date', 'timezone', 'schedule_times', 'next_run',
                                 'worker', 'batches_today', 'runner_attempts_today', 'usage_today',
                                 'usage_coverage', 'last_run', 'mailboxes', 'codex_week',
                                 'investigation_this_week', 'quota', 'investigation_quota'}


def test_unfinished_tip_names_an_existing_page_and_preserves_root(tmp_path):
    import shlex
    root = tmp_path / 'co rem with spaces'
    prepare(root)
    Notebook(root).stub_project('projects/atlas.md', 'Atlas', ['/tmp/atlas'])
    result = invoke(root, 'unfinished')
    assert result.exit_code == 0, result.output
    command = shlex.split(result.output.split('Next: ')[1].strip())
    assert command == ['co', 'rem', '--root', str(root), 'investigate', 'projects/atlas.md']


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
    monkeypatch.setattr('connectonion.rem.service.mail_client', lambda *a, **kw: SimpleNamespace(my_addresses=lambda: []))
    monkeypatch.setattr('connectonion.rem.scan.scan_people', lambda *a, **kw: rows if kind == 'people' else [])
    monkeypatch.setattr('connectonion.rem.scan.scan_orgs', lambda *a, **kw: rows)
    monkeypatch.setattr('connectonion.rem.scan.scan_projects', lambda *a, **kw: rows)
    result = invoke(tmp_path, 'scan', kind)
    assert result.exit_code == 0, result.output
    assert shlex.split(result.output.split('Next: ')[1].strip())[4:] == tail


def test_human_formatter_preserves_partial_errors_and_terminal_safety():
    from connectonion.cli.commands.rem_output import render
    result = render({'outcome': 'partial', 'errors': [{'source': 'gmail', 'error': 'Access denied'}],
                     'usage': {'input_tokens': None}, 'report': '\x1b[31m untrusted'}, 'daily', failed=True)
    assert 'needs attention' in result and 'Access denied' in result
    assert 'Input tokens: Unknown' in result
    assert '\x1b' not in result


def test_investigate_without_arguments_discovers_real_pages_without_a_model(tmp_path, monkeypatch):
    prepare(tmp_path)
    Notebook(tmp_path).stub_person('people/ody-123.md', 'Ody', ['ody@example.org'])
    monkeypatch.setattr('connectonion.rem.investigate.investigate', lambda *a, **kw: pytest.fail('model called'))
    result = invoke(tmp_path, 'investigate')
    assert result.exit_code == 0, result.output
    assert 'people/ody-123.md' in result.output          # listed under People, most useful first
    assert result.output.rstrip().endswith('investigate people')


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
    monkeypatch.setattr('connectonion.rem.service.subscriptions', lambda root: {})
    calls = []
    def run(root, record, *args, **kwargs):
        calls.append(record)
        return {'record': record, 'changed': []}
    monkeypatch.setattr('connectonion.rem.investigate.investigate', run)
    result = invoke(tmp_path, 'investigate', selector)
    assert result.exit_code == 0, result.output
    assert calls == ['people/ody-123.md']
    assert result.output.rstrip().endswith('show people/ody-123.md')


def test_ambiguous_investigation_shows_choices_without_starting(tmp_path, monkeypatch):
    prepare(tmp_path)
    for suffix in ('one', 'two'):
        Notebook(tmp_path).stub_person(f'people/ody-{suffix}.md', 'Ody', [])
    monkeypatch.setattr('connectonion.rem.investigate.investigate', lambda *a, **kw: pytest.fail('model called'))
    result = invoke(tmp_path, 'investigate', 'Ody')
    assert result.exit_code == 1, result.output
    assert 'More than one page matches' in result.output
    assert 'people/ody-one.md' in result.output and 'people/ody-two.md' in result.output
    assert result.output.rstrip().endswith(' investigate')


def test_investigate_help_does_not_run_even_with_page_argument(tmp_path, monkeypatch):
    monkeypatch.setattr('connectonion.rem.investigate.investigate', lambda *a, **kw: pytest.fail('model called'))
    result = invoke(tmp_path, 'investigate', '--help', 'people/ody.md')
    assert result.exit_code == 0
    assert result.stdout.startswith('co rem investigate —')


def test_json_investigate_discovery_and_missing_selection(tmp_path):
    discovered = json.loads(invoke(tmp_path, '--json', 'investigate').stdout)
    assert discovered['ok'] and 'No pages available' in discovered['data']
    assert discovered['next'].endswith(' init')
    result = invoke(tmp_path, '--json', 'investigate', 'missing')
    failed = json.loads(result.stdout)
    assert result.exit_code == 1 and not failed['ok']
    assert failed['next'].endswith(' investigate')


def test_a_wrapper_can_put_its_own_name_on_every_next_step(tmp_path, monkeypatch):
    """A thin `remi` command that forwards to `co rem` is only a product if the tips
    agree with it: a user who typed `remi status` and is told `co rem --root /long/path
    init` has been handed the wiring. The wrapper names itself in the environment and
    every Next line follows; the root is omitted when it is the default one."""
    monkeypatch.setenv("CO_REM_PROGRAM", "remi")
    result = runner.invoke(app, ["rem", "--root", str(tmp_path), "status"])
    assert result.exit_code == 0, result.output
    assert result.output.strip().endswith(f"Next: remi --root {tmp_path} init")
    from pathlib import Path
    default_root = Path.home() / ".co" / "rem"   # the harness already isolates HOME per test
    result = runner.invoke(app, ["rem", "--root", str(default_root), "status"])
    assert result.output.strip().endswith("Next: remi init")  # the default root is not spelled out


def test_subscribing_a_whatsapp_chat_points_at_start(tmp_path):
    """Naming a chat is not permission to read it; the next command is the one
    that shows the user what will be read and asks."""
    result = invoke(tmp_path, '--json', 'sources', 'add', 'whatsapp', '--chat', '120363411567190840@g.us')
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload['data']['chats'] == ['120363411567190840@g.us']
    assert payload['next'].endswith(' start')
    refused = invoke(tmp_path / 'fresh', 'sources', 'add', 'whatsapp')   # no chat named yet
    assert refused.exit_code == 1 and 'co whatsapp chats' in refused.output


def test_a_project_is_read_from_its_folders_not_from_mail_that_names_it(tmp_path, monkeypatch):
    """Matching mail on a project's name scanned 3,500 mails for one project on a
    real mailbox and timed out. The help page says a project is read from its
    sessions; mail about it comes in only through --handle."""
    prepare(tmp_path)
    Notebook(tmp_path).stub_project("projects/aurora.md", "Aurora", ["/work/aurora"])
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: True)
    monkeypatch.setattr('connectonion.rem.service.mail_client', lambda kind, **kw: object())
    calls = []
    def run(root, record, title, handles, **kwargs):
        calls.append((handles, sorted(kwargs['clients'])))
        return {'record': record, 'changed': []}
    monkeypatch.setattr('connectonion.rem.investigate.investigate', run)
    assert invoke(tmp_path, 'investigate', 'projects/aurora.md').exit_code == 0
    assert calls[-1] == (['/work/aurora', 'Aurora'], [])
    assert invoke(tmp_path, 'investigate', 'projects/aurora.md', '--handle', 'aurora@client.example').exit_code == 0
    assert calls[-1][1] == ['gmail', 'outlook'] and 'aurora@client.example' in calls[-1][0]


def test_an_investigation_is_a_run_in_the_logs_with_its_cost(tmp_path, monkeypatch):
    """A notebook with a dozen investigated pages said "No runs recorded": the
    co rem's most expensive calls were missing from the one command that shows cost."""
    prepare(tmp_path)
    Notebook(tmp_path).stub_person('people/ody.md', 'Ody', ['ody@example.org'], email='ody@example.org')
    monkeypatch.setattr('connectonion.rem.service.subscriptions', lambda root: {})
    monkeypatch.setattr('connectonion.rem.investigate.investigate', lambda root, record, *a, **k: {
        'record': record, 'changed': [record], 'usage': {'input_tokens': 1200, 'output_tokens': 300},
        'usage_by_stage': {'investigate': {'input_tokens': 1200, 'output_tokens': 300}}, 'chars_gathered': 4800})
    assert invoke(tmp_path, 'investigate', 'people/ody.md').exit_code == 0
    runs = json.loads(invoke(tmp_path, '--json', 'logs').stdout)['data']
    assert runs[0]['phase'] == 'investigate' and runs[0]['record'] == 'people/ody.md'
    assert runs[0]['outcome'] == 'completed' and runs[0]['runner_attempts'] == 0   # not the background cap
    usage = json.loads(invoke(tmp_path, '--json', 'logs', '--usage').stdout)['data']
    assert usage['total']['input_tokens'] == 1200 and usage['by_stage']['investigate']['output_tokens'] == 300


def test_investigation_source_failure_is_structured_and_keeps_run(tmp_path, monkeypatch):
    from connectonion.rem.files import state_path, write_json

    prepare(tmp_path)
    Notebook(tmp_path).stub_person('people/ada.md', 'Ada', ['ada@example.org'], email='ada@example.org')
    write_json(state_path(tmp_path, 'map.json'), {
        'owner': {'record': 'people/ada.md', 'addresses': ['ada@example.org']}})
    monkeypatch.setattr('connectonion.rem.service.subscriptions', lambda root: {})
    monkeypatch.setattr('connectonion.rem.investigate.gather',
                        lambda *a, **kw: (_ for _ in ()).throw(ConnectionError('private provider detail')))
    result = invoke(tmp_path, '--json', 'investigate', 'me', '--days', '5')
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload['ok'] is False
    assert 'ConnectionError' in payload['data'] and 'private provider detail' not in result.stdout
    assert payload['next'].endswith('investigate me --days 5')
    run = json.loads(next((tmp_path / '.state/runs').glob('*.json')).read_text())
    assert run['outcome'] == 'failed' and run['stage'] == 'gathering sources'


def test_interrupted_investigation_keeps_completed_chunk_usage(tmp_path):
    from connectonion.cli.commands.rem_commands import _logged

    prepare(tmp_path)

    def interrupt(update):
        update('extracting long evidence', 2, 5, {'input_tokens': 1200})
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _logged(tmp_path, 'people/owner.md', 'investigate me', interrupt)
    run = json.loads(next((tmp_path / '.state/runs').glob('*.json')).read_text())
    assert run['outcome'] == 'interrupted'
    assert run['stage_processed'] == 2 and run['stage_total'] == 5
    assert run['usage'] == {'input_tokens': 1200}


def test_category_run_reports_partial_failure_nonzero(tmp_path, monkeypatch):
    prepare(tmp_path)
    Notebook(tmp_path).stub_person('people/ada.md', 'Ada', ['ada@example.org'], email='ada@example.org')
    monkeypatch.setattr('connectonion.rem.queue.order', lambda root, category: [
        {'path': 'people/ada.md', 'recent': False, 'weight': 1, 'unknown': 1,
         'last_investigated': None}])
    from connectonion.rem.runner import RunFailed
    monkeypatch.setattr('connectonion.rem.investigate.investigate',
                        lambda *a, **kw: (_ for _ in ()).throw(RunFailed('model rejected')))
    result = invoke(tmp_path, '--json', 'investigate', 'people', '--days', '5', '--limit', '1')
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload['ok'] is False
    assert payload['data']['pages'][0]['outcome'] == 'refused'


def test_an_error_that_names_a_command_makes_it_the_next_line(tmp_path):
    """`sync` before `start` said "run co rem start" and printed Next: co rem logs."""
    prepare(tmp_path)
    result = invoke(tmp_path, 'sync')
    assert result.exit_code == 1 and 'co rem start' in result.output
    assert result.output.rstrip().endswith(f'--root {tmp_path} start')


def test_list_without_a_category_is_refused_before_anything_runs(tmp_path):
    result = invoke(tmp_path, 'investigate', '--list')
    assert result.exit_code == 1 and 'investigate people --list' in result.output


def test_start_help_names_the_confinement_and_the_undo():
    import re
    result = runner.invoke(app, ["rem", "start", "--help"])
    text = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "--sandbox workspace-write" in text and "--permission-mode acceptEdits" in text
    assert "co rem stop" in text


def test_a_second_start_says_why_it_ran_no_batch(lifecycle):
    """After stop, `start` resumed the schedule and printed `First batch:
    Unknown` while its help promised it runs the first update. Only the first
    start runs one; the output says so and names the command that runs one now."""
    root, sessions, calls = lifecycle
    assert invoke(root, "start", "--yes").exit_code == 0
    assert invoke(root, "stop").exit_code == 0
    again = invoke(root, "start", "--yes")
    assert again.exit_code == 0, again.output
    assert "First batch: Unknown" not in again.output
    assert "sync" in again.output.split("First batch:")[1].splitlines()[0]
    assert json.loads(invoke(root, "--json", "start", "--yes").stdout)["data"]["first_batch"] is None


def test_init_with_only_a_name_makes_your_page_and_says_what_investigate_me_needs(tmp_path, monkeypatch):
    """`init --name` with no mailbox made no owner page, so `investigate me`
    said "Run init first" to someone who had; and `list people` right after
    init said "Run init to build the map". Each now says what is true."""
    monkeypatch.setattr('connectonion.rem.service.subscriptions', lambda root: {})
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: False)
    monkeypatch.setattr('connectonion.rem.runner.run_stage', lambda *a, **kw: pytest.fail('no model without material'))
    empty = tmp_path / 'empty-skills'
    empty.mkdir()
    bare = tmp_path / 'bare'
    assert invoke(bare, 'init', '--skills-dir', str(empty)).exit_code == 0
    listing = invoke(bare, 'list', 'people')
    assert 'Run init to build the map' not in listing.output
    assert 'co auth google' in listing.output and 'mailbox' in listing.output

    result = invoke(tmp_path, '--json', 'init', '--skills-dir', str(empty), '--name', 'Test User')
    assert result.exit_code == 0, result.output
    record = json.loads(result.output)['data']['owner']['record']
    assert (tmp_path / record).read_text().startswith('# Test User\n')
    me = invoke(tmp_path, 'investigate', 'me')
    assert me.exit_code == 1
    assert 'Run init first' not in me.output
    assert record in me.output and 'co auth google' in me.output


def test_sources_on_a_fresh_notebook_lists_whatsapp(tmp_path):
    result = invoke(tmp_path / 'fresh', 'sources')
    assert result.exit_code == 0, result.output
    assert 'whatsapp' in result.output.lower()


@pytest.mark.parametrize('make', ['symlink', 'oversize', 'not_utf8', 'hidden'])
def test_investigate_a_bad_file_gives_the_reason_show_gives(tmp_path, make):
    """`show` named why a file is not a page; `investigate` on the same path
    said only "No page matches", which sent people looking for a typo."""
    prepare(tmp_path)
    people = tmp_path / 'people'
    people.mkdir(exist_ok=True)
    name = {'hidden': '._page.md'}.get(make, f'{make}.md')
    target = people / name
    if make == 'symlink':
        outside = tmp_path / 'outside.md'
        outside.write_text('# Outside\n')
        target.symlink_to(outside)
    elif make == 'oversize':
        target.write_text('# Big\n' + 'x' * (2 * 1024 * 1024))
    elif make == 'not_utf8':
        target.write_bytes(b'\xff\xfe\xfdnot utf8\n')
    else:
        target.write_bytes(b'\x00\x05\x16\x07')
    record = f'people/{name}'
    shown = invoke(tmp_path, 'show', record)
    investigated = invoke(tmp_path, 'investigate', record)
    assert shown.exit_code == investigated.exit_code == 1
    assert 'No page matches' not in investigated.output
    reason = [line for line in shown.output.splitlines() if line.startswith('Error:')][0]
    assert reason in investigated.output


def test_doctor_says_whether_spreadsheet_support_is_installed(tmp_path, monkeypatch):
    import importlib.util
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, 'find_spec',
                        lambda name, *a: None if name == 'openpyxl' else real(name, *a))
    result = invoke(tmp_path, 'doctor')
    line = next(line for line in result.output.splitlines() if 'spreadsheet' in line)
    assert line.startswith('NO') and "connectonion[rem]" in line


def test_a_batch_with_nothing_to_warn_about_prints_no_empty_warning_line():
    from connectonion.cli.commands.rem_output import render
    quiet = render({"outcome": "completed", "warning": ""}, "sync")
    assert "Warning" not in quiet
    loud = render({"outcome": "completed", "warning": "codex: 3 messages in an unfamiliar format were not read"}, "sync")
    assert "Warning: codex: 3 messages" in loud


# ---------------------------------------------------------- #1974: misleading lines


def test_config_does_not_suggest_setting_the_model_that_is_already_set(tmp_path):
    prepare(tmp_path)
    result = invoke(tmp_path, "config")
    assert result.exit_code == 0, result.output
    assert result.output.strip().splitlines()[-1].endswith("status")
    assert "same model" in result.output


def test_doctor_says_a_connected_mailbox_the_round_does_not_read(tmp_path, monkeypatch):
    prepare(tmp_path)
    monkeypatch.setattr('connectonion.rem.service.mail_available', lambda kind: kind == 'gmail')
    result = invoke(tmp_path, 'doctor')
    line = next(line for line in result.output.splitlines() if 'mailbox gmail' in line)
    assert line.startswith('NO') and 'not read by the daily round' in line and 'sources add gmail' in line


def test_the_overview_help_names_projects_among_the_advanced_commands(tmp_path):
    result = invoke(tmp_path, "--help")
    advanced = result.output[result.output.index("Advanced:"):result.output.index("Old names:")]
    assert "projects" in advanced


def test_status_ends_on_the_step_its_first_line_names(tmp_path, monkeypatch):
    """A notebook never started read "run co rem start" and then "Next: co rem logs"."""
    from connectonion.cli.commands.rem_status import status_next
    assert status_next({"configured": False, "state": "Not started"}) == ["init"]
    assert status_next({"configured": True, "state": "Not started — run `co rem start`"}) == ["start"]
    assert status_next({"configured": True, "state": "Stopped — background maintenance is off"}) == ["start"]
    assert status_next({"configured": True, "state": "Running in background (launchd); next slot 07:00"}) == ["logs"]
