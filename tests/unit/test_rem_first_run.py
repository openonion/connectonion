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
import re
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
    progress = [line for line in result.output.splitlines() if line.startswith("✓ ")]
    assert 3 <= len(progress) <= 8, progress
    assert not any("listed gmail mail 20" in line for line in progress)
    log = (root / ".state/init-progress.log").read_text()
    assert log.count("listed gmail mail") >= 13  # every seven-day window is still recorded


class Terminal(io.StringIO):
    def isatty(self):
        return True


def test_a_terminal_sees_a_bar_per_stage_and_each_finished_stage_once():
    """#1996: 90 days is thirteen seven-day windows, so listing mail is a bar that fills;
    each stage's finished line stays, once, above the next stage's bar."""
    from connectonion.cli.commands.rem_output import StageProgress

    screen = Terminal()
    progress = StageProgress(stream=screen, days=90)
    for week in range(13):
        progress(f"listed gmail mail 2026-0{1 + week % 9}-01 to 2026-0{1 + week % 9}-08", 4)
    progress("scanned gmail mail metadata", 3)
    progress("scanning local projects")
    progress("scanning local projects (codex sessions)", "50/80")
    progress("mapped projects", 2)
    progress.close()
    shown = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", screen.getvalue())
    assert "━" in shown and "13/13" in shown and "50/80" in shown
    assert shown.count("✓ ") == 2
    assert "✓ gmail: 52 messages listed, 3 correspondents" in shown


def test_a_model_turn_is_a_spinner_with_its_time_in_a_terminal_and_lines_elsewhere(capsys):
    from connectonion.cli.commands.rem_output import Turn

    screen = Terminal()
    with Turn("Writing your page…", stream=screen) as turn:
        turn.stage("gathering sources")
    shown = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", screen.getvalue())
    assert "Writing your page… (gathering sources)" in shown and re.search(r"\d:\d\d:\d\d", shown)
    with Turn("Writing your page…", stream=io.StringIO()) as turn:
        turn.stage("gathering sources")
    assert capsys.readouterr().err == "Investigation: gathering sources\n"


# ---------------------------------------------------- investigating me


def test_runner_ok_investigates_me_once_with_inits_window(first_run):
    root, init, calls = first_run
    result = init("--days", "5")
    assert result.exit_code == 0, result.output
    assert [call["record"] for call in calls].count(owner_record(root)) == 1
    call = calls[0]
    assert call["record"] == owner_record(root)
    # The whole page, not the pre-#1850 quick pass (owner, 2026-09-30).
    assert call["days"] == 5 and call["quick"] is False and call["sent_only"] is True
    assert "me@example.org" in call["handles"]
    text = Text.from_ansi(result.output).plain
    assert "codex" in text and "gpt-6-luna" in text
    assert "your own" in text and "Ctrl-C" in text
    assert text.rstrip().endswith(f"--root {root} open")
    assert f"--root {root} start" in text


def test_init_ends_with_what_is_in_the_notebook_what_was_written_and_what_is_next(first_run):
    """#1996: the map's counts scrolled away under the model turn; the last lines say them again, skills included."""
    root, init, _ = first_run
    result = init()
    assert result.exit_code == 0, result.output
    tail = result.output.rstrip().splitlines()[-5:]
    assert tail[0] == "Your notebook: 4 people, 3 organizations, 0 projects and 0 skills."
    assert tail[1] == "Written this run: your page and 1 person."
    assert tail[2].startswith("Your page: ") and tail[2].endswith(".md")
    assert tail[3].startswith(f"Then keep it current: co rem --root {root} start")
    assert tail[4] == f"Next: co rem --root {root} open"


def test_default_window_matches_the_old_next_command(first_run):
    _, init, calls = first_run
    assert init().exit_code == 0
    assert calls[0]["days"] == 30  # `investigate me` without --days


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
    assert "investigate me --days 5" in text and "--quick" not in text


def test_json_with_investigate_runs_it_and_stays_machine_readable(first_run):
    root, init, calls = first_run
    result = init("--json", "--investigate")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert calls[0]["record"] == owner_record(root)
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
    assert payload["next"].endswith("investigate me --days 5")
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
    assert calls[0]["record"] == owner_record(root)  # me first, then the people
    assert written == ["projects/alpha.md", "projects/beta.md"]  # the old one waits
    text = Text.from_ansi(result.output).plain
    # One total before the first page (#2008), from measured defaults on a notebook with no runs yet.
    assert "About 4 pages (your page, 1 person and 2 projects), ~2.6M billed input tokens" in text
    assert "an estimate from runs measured on a real notebook" in text and "Ctrl-C" in text
    assert text.count("billed input tokens") == 1
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


# ------------------------------------------- the people you write to, after me


@pytest.fixture
def people(projects, monkeypatch):
    """Five people in the queue, most-written-to first, and a spy where each person's turn would be."""
    (root, init, calls), written = projects
    rows = [{"record": f"people/p{n}.md", "mode": "full", "days": 150, "last_activity": "2026-09-29T00:00:00Z",
             "recent": True, "mails": 10 - n, "sent": 3, "received": 3, "last_investigated": None}
            for n in range(5)]
    people_written = []
    monkeypatch.setattr("connectonion.rem.people_pages.queue",
                        lambda root, **kw: [row for row in rows if row["record"] not in people_written])

    def investigate_person(root, row, **kw):
        people_written.append(row["record"])
        return {"record": row["record"], "changed": [row["record"]]}

    monkeypatch.setattr("connectonion.rem.people_pages.investigate_person", investigate_person)
    return root, init, calls, people_written, written


def test_after_me_the_three_people_written_to_most_then_projects(people):
    """Owner, 2026-09-30: the first run shows the people around you, not only you."""
    root, init, calls, people_written, projects_written = people
    result = init()
    assert result.exit_code == 0, result.output
    assert [call["record"] for call in calls] == [owner_record(root)]
    assert people_written == ["people/p0.md", "people/p1.md", "people/p2.md"]
    assert projects_written == ["projects/alpha.md", "projects/beta.md"]
    text = Text.from_ansi(result.output).plain
    assert "the 3 people you wrote to most in the last 14 days, from the last 90 days of their mail" in text
    assert "About 6 pages (your page, 3 people and 2 projects)" in text and "Investigating" not in text
    assert "It stops at 5 points of the Codex week" in text
    assert "Written this run: your page, 3 people and 2 project pages." in text


def test_the_first_run_stops_at_its_five_points_and_keeps_what_is_written(people, monkeypatch):
    root, init, calls, people_written, projects_written = people
    meter = {"used_percent": 10, "window_minutes": 10080, "resets_at": 4102444800, "plan": "plus"}
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: dict(meter))

    def one_person_costs_six_points(root, row, **kw):
        people_written.append(row["record"])
        meter["used_percent"] += 6
        return {"record": row["record"], "changed": [row["record"]]}

    monkeypatch.setattr("connectonion.rem.people_pages.investigate_person", one_person_costs_six_points)
    result = init("--json", "--investigate")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert people_written == ["people/p0.md"]
    assert "used 6 of its 5 points" in data["people_pages"]["stopped"]
    assert projects_written == []
    assert "used 6 of its 5 points" in data["project_pages"]["reason"]


def test_ctrl_c_during_people_keeps_the_pages_and_names_the_rest(people, monkeypatch):
    root, init, calls, people_written, _ = people

    def interrupted(root, row, **kw):
        if people_written:
            raise KeyboardInterrupt
        people_written.append(row["record"])
        return {"record": row["record"], "changed": [row["record"]]}

    monkeypatch.setattr("connectonion.rem.people_pages.investigate_person", interrupted)
    result = init()
    assert result.exit_code == 130
    assert people_written == ["people/p0.md"]
    assert f"--root {root} investigate people" in Text.from_ansi(result.output).plain


# ------------------------------------------- what the first run spends (#2008)


def test_the_first_run_is_capped_and_a_flag_raises_the_cap(people, monkeypatch):
    """1.9.0a5 queued every project active in the window: 13 on a real notebook."""
    root, init, calls, people_written, projects_written = people
    rows = [{"record": f"projects/p{n}.md", "mode": "first", "last_activity": "2026-09-29T00:00:00Z",
             "recent": True, "new_messages": 1, "chars": 100, "left_out": 0} for n in range(5)]
    monkeypatch.setattr("connectonion.rem.project_pages.queue",
                        lambda root, **kw: [row for row in rows if row["record"] not in projects_written])
    assert init().exit_code == 0
    assert projects_written == ["projects/p0.md", "projects/p1.md", "projects/p2.md"]
    assert len(people_written) == 3
    projects_written.clear()
    people_written.clear()
    result = init("--first-projects", "5", "--first-people", "1", "--json", "--investigate")
    assert result.exit_code == 0, result.output
    assert len(projects_written) == 5 and people_written == ["people/p0.md"]
    plan = json.loads(result.stdout)["data"]["first_run"]
    assert plan["counts"] == {"owner": 1, "person": 1, "project": 5}


def test_first_run_people_read_the_runs_own_window_not_150_days(people, monkeypatch):
    root, init, calls, people_written, _ = people
    seen = []

    def investigate_person(root, row, **kw):
        seen.append(row["days"])
        people_written.append(row["record"])
        return {"record": row["record"], "changed": [row["record"]]}

    monkeypatch.setattr("connectonion.rem.people_pages.investigate_person", investigate_person)
    result = init("--days", "7")
    assert result.exit_code == 0, result.output
    assert seen == [7, 7, 7]
    assert "the last 7 days, from the last 7 days of their mail" in Text.from_ansi(result.output).plain


def test_the_estimate_is_the_median_of_this_notebooks_own_runs():
    from connectonion.rem import first_run as fr

    def run(phase, record, tokens, seconds, outcome="completed"):
        return {"phase": phase, "record": record, "outcome": outcome, "seconds": seconds,
                "usage": {"input_tokens": tokens}}

    runs = [run("projects write", "projects/a.md", 614_000, 240), run("projects write", "projects/b.md", 922_000, 300),
            run("projects write", "projects/c.md", 700_000, 270),
            run("projects write", "projects/d.md", 9_000_000, 900, outcome="interrupted"),
            run("investigate", "orgs/x.md", 5_000_000, 999)]
    assert fr.per_page(runs, "project") == {"input_tokens": 700_000, "seconds": 270, "measured": 3}
    assert fr.per_page(runs, "person") == {**fr.DEFAULTS["person"], "measured": 0}
    total = fr.plan(runs, owner=False, people=0, projects=2)
    assert total["input_tokens"] == 1_400_000 and total["minutes"] == 9
    line = fr.announce(total, "on your Codex plan")
    assert line == ("About 2 pages (2 projects), ~1.4M billed input tokens on your Codex plan, ~9 minutes "
                    "(an estimate from this notebook's own runs).")
    mixed = fr.announce(fr.plan(runs, owner=True, people=1, projects=1), "on your Codex plan")
    assert "About 3 pages (your page, 1 person and 1 project)" in mixed and "measured defaults otherwise" in mixed


def test_ctrl_c_says_what_was_written_and_what_continues(people, monkeypatch):
    root, init, calls, people_written, projects_written = people

    def second_project_is_stopped(root, record, **kw):
        if projects_written:
            raise KeyboardInterrupt
        projects_written.append(record)
        return {"record": record, "changed": [record]}

    monkeypatch.setattr("connectonion.rem.project_pages.write_page", second_project_is_stopped)
    result = init()
    assert result.exit_code == 130
    text = Text.from_ansi(result.output).plain
    assert "Stopped: 5 pages written before the stop" in text
    assert "projects/alpha.md), and kept." in text
    assert f"Next: co rem --root {root} projects write" in text
