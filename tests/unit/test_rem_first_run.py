"""The first run is one command with value in the first minutes (#1943).

The owner's own first run (2026-09-25) took ten minutes, wrote a 15,498-line
log, made 370 empty people pages, ended with twelve separate `--mine`
questions and then needed a second command nobody had told him about. The
owner decided: init is a script that saves the raw material, the facts it
already knows about you are printed right away, and investigating your own
page starts by itself -- after saying what it will spend -- unless there is a
reason not to, which it gives in one line.

Everything here runs on fakes: a fake mailbox, a fake runner check and a fake
investigation. No network, no Codex.
"""

import io
import json

import pytest
from rich.text import Text
from typer.testing import CliRunner

from connectonion.cli.main import app

runner = CliRunner()


class Mail:
    """A mailbox with 90 days of mail: Bob writes and is answered every week, and
    two addresses the owner writes to never reply (possibly the owner's own)."""

    def my_addresses(self):
        return {"me@example.org"}

    def my_name(self):
        return "Ada Owner"

    def list_between(self, start, end, limit):
        day = start[:10]
        return [
            {"id": f"{day}-in", "date": start, "from": "Bob Stone <bob@partner.example>",
             "to": ["me@example.org"], "subject": "Plan"},
            {"id": f"{day}-out", "date": start, "from": "me@example.org",
             "to": ["bob@partner.example"], "subject": "Re: Plan"},
            {"id": f"{day}-self", "date": start, "from": "me@example.org",
             "to": ["ada.personal@example.net"], "subject": "note to self"},
            {"id": f"{day}-self2", "date": start, "from": "me@example.org",
             "to": ["ada.backup@example.com"], "subject": "backup"},
        ]

    def get_email_body(self, message_id):
        return "--- Email Body ---\nbody of " + message_id


@pytest.fixture
def first_run(tmp_path, monkeypatch):
    """A root with one connected mailbox (gmail), an isolated runner and a spy
    where the model would be."""
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: kind == "gmail")
    monkeypatch.setattr("connectonion.rem.service.mail_client", lambda kind, **kw: Mail())
    calls = []

    def investigate(root, record, subject, handles, **kw):
        calls.append({"record": record, "handles": handles, **kw})
        return {"record": record, "changed": [record], "items": 3}

    monkeypatch.setattr("connectonion.rem.investigate.investigate", investigate)
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("", ""))
    monkeypatch.setattr("connectonion.cli.commands.rem_commands._interactive", lambda: True)
    skills = tmp_path / "empty-skills"
    skills.mkdir()
    root = tmp_path / "rem"

    def init(*args):
        result = runner.invoke(app, ["rem", "--root", str(root), *[a for a in args if a == "--json"],
                                     "init", "--skills-dir", str(skills),
                                     *[a for a in args if a != "--json"]])
        return result

    return root, init, calls


def owner_record(root):
    return json.loads((root / ".state/map.json").read_text())["owner"]["record"]


# ------------------------------------------------------------ value first


def test_the_owners_page_is_printed_with_where_it_lives(first_run):
    root, init, _ = first_run
    result = init("--no-investigate")
    assert result.exit_code == 0, result.output
    text = Text.from_ansi(result.stdout).plain
    record = owner_record(root)
    assert "Ada Owner" in text
    assert "Most mail with: Bob Stone" in text
    assert "wrote" in text and "received" in text
    assert str(root / record) in text


def test_json_carries_the_owner_page_and_stays_one_object(first_run):
    root, init, calls = first_run
    result = init("--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    page = payload["data"]["owner_page"]
    assert page["record"] == owner_record(root)
    assert any("Most mail with: Bob Stone" in fact for fact in page["facts"])
    assert payload["data"]["investigation"] == "not started"
    assert calls == []  # --json never runs a model unless asked


# ------------------------------------------------------- own addresses


def test_possible_own_addresses_are_one_line_and_one_command(first_run):
    root, init, _ = first_run
    result = init("--json", "--no-investigate")
    asked = json.loads(result.stdout)["data"]["confirm_own_addresses"]
    commands = [line for line in asked if "init --mine" in line]
    assert len(commands) == 1
    assert "--mine ada.backup@example.com,ada.personal@example.net" in commands[0]
    plain = init("--no-investigate")
    assert Text.from_ansi(plain.output).plain.count("init --mine") == 1


def test_mine_accepts_several_addresses_in_one_run(first_run):
    root, init, _ = first_run
    result = init("--json", "--no-investigate", "--mine", "ada.personal@example.net,ada.backup@example.com")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert set(data["owner"]["addresses"]) >= {"ada.personal@example.net", "ada.backup@example.com"}
    assert not data["possible_own_addresses"]


# -------------------------------------------------------- subscriptions


def test_mailboxes_init_read_are_subscribed_for_start(first_run):
    from connectonion.rem.service import consent_summary, subscriptions
    root, init, _ = first_run
    assert init("--no-investigate").exit_code == 0
    sources = subscriptions(root)
    assert sources["gmail"]["enabled"] is True
    assert sources["gmail"]["consented"] is False  # start still asks
    assert sources["outlook"]["enabled"] is False  # never read, never subscribed
    assert consent_summary(root)["sources"]["gmail"]["state"].startswith("will be read")


# --------------------------------------------------------------- progress


def test_a_90_day_scan_prints_a_handful_of_lines_and_logs_the_rest(first_run):
    root, init, _ = first_run
    result = init("--no-investigate")
    assert result.exit_code == 0, result.output
    progress = [line for line in result.output.splitlines() if line.startswith("co rem init:")]
    assert 3 <= len(progress) <= 8, progress
    assert not any("listed gmail mail 20" in line for line in progress)
    log = (root / ".state/init-progress.log").read_text()
    assert log.count("listed gmail mail") >= 13  # every seven-day window is still recorded


def test_a_terminal_sees_each_stage_updated_in_place():
    from connectonion.cli.commands.rem_output import StageProgress

    class Terminal(io.StringIO):
        def isatty(self):
            return True

    screen = Terminal()
    progress = StageProgress(stream=screen)
    for week in range(13):
        progress(f"listed gmail mail 2026-0{1 + week % 9}-01 to 2026-0{1 + week % 9}-08", 4)
    progress("scanned gmail mail metadata", 3)
    progress("scanning local projects")
    progress("mapped projects", 2)
    progress.close()
    assert "\r" in screen.getvalue()
    assert screen.getvalue().count("\n") == 2  # one finished line per stage


# ---------------------------------------------------- investigating me


def test_runner_ok_investigates_me_once_with_inits_window(first_run):
    root, init, calls = first_run
    result = init("--days", "5")
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    call = calls[0]
    assert call["record"] == owner_record(root)
    assert call["days"] == 5 and call["quick"] is True and call["sent_only"] is True
    assert "me@example.org" in call["handles"]
    text = Text.from_ansi(result.output).plain
    assert "codex" in text and "gpt-6-luna" in text
    assert "your own" in text and "Ctrl-C" in text
    assert text.rstrip().endswith(f"--root {root} open")
    assert f"--root {root} start" in text


def test_default_window_matches_the_old_next_command(first_run):
    _, init, calls = first_run
    assert init().exit_code == 0
    assert calls[0]["days"] == 30  # `investigate me --quick` without --days


def test_runner_missing_says_so_once_and_does_not_investigate(first_run, monkeypatch):
    monkeypatch.setattr("connectonion.rem.runner.ready",
                        lambda config: ("Codex is not signed in", "codex login"))
    _, init, calls = first_run
    result = init("--investigate")
    assert result.exit_code == 0, result.output
    assert calls == []
    text = Text.from_ansi(result.output).plain
    assert text.count("Codex is not signed in") == 1
    assert "codex login" in text


def test_no_investigate_builds_the_map_only(first_run):
    _, init, calls = first_run
    result = init("--json", "--no-investigate")
    assert result.exit_code == 0
    assert calls == []
    data = json.loads(result.stdout)
    assert "--no-investigate" in data["data"]["investigate_me"]["reason"]
    assert data["next"].endswith(" open")


def test_not_a_terminal_means_not_by_default(first_run, monkeypatch):
    monkeypatch.setattr("connectonion.cli.commands.rem_commands._interactive", lambda: False)
    root, init, calls = first_run
    result = init("--days", "5")
    assert result.exit_code == 0, result.output
    assert calls == []
    text = Text.from_ansi(result.output).plain
    assert "--investigate" in text
    assert "investigate me --days 5 --quick" in text


def test_json_with_investigate_runs_it_and_stays_machine_readable(first_run):
    root, init, calls = first_run
    result = init("--json", "--investigate")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert len(calls) == 1
    assert payload["data"]["investigation"] == "completed"
    assert payload["data"]["investigate_me"]["page"] == owner_record(root)


def test_a_rerun_does_not_pay_for_a_page_already_written(first_run):
    root, init, calls = first_run
    assert init("--no-investigate").exit_code == 0
    page = root / owner_record(root)
    lines = [("Investigation: investigated 2026-09-30" if line.startswith("Investigation:") else line)
             for line in page.read_text().splitlines()]
    page.write_text("\n".join(lines) + "\n")
    result = init("--json")
    assert result.exit_code == 0, result.output
    assert calls == []
    assert "already" in json.loads(result.stdout)["data"]["investigate_me"]["reason"]


def test_no_mail_address_of_mine_skips_with_a_reason(first_run, monkeypatch):
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    _, init, calls = first_run
    result = init("--json", "--investigate")
    assert result.exit_code == 0, result.output
    assert calls == []
    assert "co auth google" in json.loads(result.stdout)["data"]["investigate_me"]["reason"]


def test_a_failed_first_page_keeps_the_map_and_names_the_retry(first_run, monkeypatch):
    from connectonion.rem.runner import RunFailed

    def refuse(*a, **kw):
        raise RunFailed("the runner stopped")

    monkeypatch.setattr("connectonion.rem.investigate.investigate", refuse)
    root, init, _ = first_run
    result = init("--json", "--investigate", "--days", "5")
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["data"]["investigation"] == "failed"
    assert payload["next"].endswith("investigate me --days 5 --quick")
    assert (root / "notes/people-map.md").is_file()


# ------------------------------------------------------- runner preflight


def test_runner_preflight_checks_path_and_sign_in_without_a_model(tmp_path, monkeypatch):
    import importlib

    from connectonion.rem import runner as rem_runner
    from connectonion.rem.config import default_config

    # The package exports a `codex` function that shadows the module's name.
    codex = importlib.import_module("connectonion.useful_tools.codex")
    config = default_config()
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    monkeypatch.setattr(codex, "_base_command", lambda: None)
    problem, fix = rem_runner.ready(config)
    assert "not installed" in problem and "npm install -g @openai/codex" in fix
    monkeypatch.setattr(codex, "_base_command", lambda: ["/bin/codex", "app-server"])
    problem, fix = rem_runner.ready(config)
    assert "not signed in" in problem and fix == "codex login"
    (tmp_path / "codex").mkdir()
    (tmp_path / "codex/auth.json").write_text("{}")
    assert rem_runner.ready(config) == ("", "")


# ------------------------------------------- recent projects, after me


@pytest.fixture
def projects(first_run, monkeypatch):
    """Two projects active this fortnight and one older, with a spy where the model would write."""
    rows = [{"record": f"projects/{name}.md", "mode": "first", "last_activity": "2026-09-29T00:00:00Z",
             "recent": recent, "new_messages": 4, "chars": 2000, "left_out": 0}
            for name, recent in (("alpha", True), ("beta", True), ("old", False))]
    written = []
    monkeypatch.setattr("connectonion.rem.project_material.extract", lambda root, subs, **kw: {})
    monkeypatch.setattr("connectonion.rem.project_pages.queue",
                        lambda root, **kw: [row for row in rows if row["record"] not in written])

    def write_page(root, record, **kw):
        written.append(record)
        return {"record": record, "changed": [record]}

    monkeypatch.setattr("connectonion.rem.project_pages.write_page", write_page)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {"unknown": "no meter in tests"})
    return first_run, written


def test_after_me_the_recent_projects_are_written_one_line_each(projects):
    (root, init, calls), written = projects
    result = init()
    assert result.exit_code == 0, result.output
    assert len(calls) == 1  # me first
    assert written == ["projects/alpha.md", "projects/beta.md"]  # the old one waits
    text = Text.from_ansi(result.output).plain
    assert "~180k billed input tokens" in text and "Cost:" in text and "Ctrl-C" in text
    assert text.count(": written") == 2
    assert "projects/old.md" not in text


def test_projects_follow_the_same_skip_rules(projects, monkeypatch):
    (root, init, calls), written = projects
    assert init("--no-investigate").exit_code == 0
    data = json.loads(init("--json").stdout)["data"]
    assert "--json" in data["project_pages"]["reason"]
    monkeypatch.setattr("connectonion.cli.commands.rem_commands._interactive", lambda: False)
    assert init().exit_code == 0
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("Codex is not signed in", "codex login"))
    missing = init("--investigate")
    assert Text.from_ansi(missing.output).plain.count("Codex is not signed in") == 1
    assert written == []


def test_json_with_investigate_writes_projects_and_reports_them(projects):
    (root, init, calls), written = projects
    result = init("--json", "--investigate")
    assert result.exit_code == 0, result.output
    pages = json.loads(result.stdout)["data"]["project_pages"]
    assert pages["started"] and [row["page"] for row in pages["pages"]] == written == [
        "projects/alpha.md", "projects/beta.md"]


def test_the_weekly_floor_stops_project_pages(projects, monkeypatch):
    (root, init, calls), written = projects
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {
        "used_percent": 90, "window_minutes": 10080, "resets_at": 4102444800, "plan": "plus"})
    result = init()
    assert result.exit_code == 0, result.output
    assert written == []
    assert "70% floor" in Text.from_ansi(result.output).plain
