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
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: kind == "gmail")
    monkeypatch.setattr("connectonion.rem.service.mail_client", lambda kind, **kw: Mail())
    calls = []

    def investigate(root, record, subject, handles, **kw):
        calls.append({"record": record, "handles": handles, **kw})
        return {"record": record, "changed": [record], "items": 3}

    monkeypatch.setattr("connectonion.rem.investigate.investigate", investigate)
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("", ""))
    monkeypatch.setattr("connectonion.rem.runner.model_access", lambda root, config: ("", ""))
    # Init also abstracts accepted pages; keep that model turn offline too.
    monkeypatch.setattr("connectonion.rem.runner.run_stage", lambda *args, **kwargs: {"changed": [], "usage": None})
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


def test_model_denial_stops_first_run_before_writing_pages(first_run, monkeypatch):
    root, init, calls = first_run
    monkeypatch.setattr("connectonion.rem.runner.model_access",
                        lambda root, config: ("provider returned 403", "claude auth login"))
    result = init("--json")
    assert result.exit_code == 1
    data = json.loads(result.stdout)["data"]
    assert data["model_access"]["ready"] is False
    assert data["background"]["started"] is False
    assert "needs attention" in data["background"]["reason"]
    assert calls == []
    assert (root / ".state/map.json").exists()
    from connectonion.rem.service import run_logs
    assert run_logs(root)[0]["phase"] == "model access"
    assert run_logs(root)[0]["outcome"] == "failed"
    assert run_logs(root)[0]["speed"] == "fast"
    assert run_logs(root)[0]["harness"] == "codex"


def test_provider_denial_stops_dispatching_the_remaining_pages():
    from connectonion.cli.commands.rem_commands import _in_parallel
    from connectonion.rem.runner import RunFailed
    started = []

    def denied():
        started.append("first")
        raise RunFailed("API Error: 403 Request not allowed")

    jobs = [{"record": "people/first.md", "mode": "full", "run": denied},
            {"record": "people/second.md", "mode": "full", "run": lambda: started.append("second")}]
    outcomes, stopped = _in_parallel(jobs, workers=1, gate=lambda: "", done=lambda job, outcome: None)
    assert started == ["first"]
    assert len(outcomes) == 1 and outcomes[0][1]["outcome"] == "failed"
    assert "model denied access" in stopped


def test_init_investigates_skills_and_reports_them_in_plan_and_summary(first_run, monkeypatch):
    root, init, _ = first_run
    folder = root.parent / 'empty-skills' / 'example'
    folder.mkdir()
    (folder / 'SKILL.md').write_text('---\nname: example\ndescription: Review one artifact.\n---\nRead the artifact and cite an issue.')
    reviewed = []
    def investigate(root, record, directories):
        reviewed.append(record)
        return {'record': record, 'changed': [record], 'usage': {'input_tokens': 100}}
    monkeypatch.setattr('connectonion.rem.skill_runs.investigate_skill_page', investigate)
    result = init('--json', '--first-people', '0', '--first-projects', '0', '--first-orgs', '0', '--first-skills', '1')
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)['data']
    assert reviewed == ['skills/catalog/example.md']
    assert data['first_run']['counts']['skill'] == 1
    assert data['first_run']['skills'] == reviewed
    assert data['skill_pages']['left'] == 0
    assert data['skill_pages']['pages'][0]['outcome'] == 'accepted'
    reviewed.clear()
    result = init('--json', '--first-people', '0', '--first-projects', '0', '--first-orgs', '0', '--first-skills', '0')
    assert result.exit_code == 0, result.output
    assert reviewed == []


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
    assert payload["data"]["investigation"] == "completed"
    assert calls[0]["record"] == owner_record(root)


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


@pytest.mark.parametrize('json_out', [False, True])
def test_non_tty_init_names_skipped_sessions_and_approval_command(first_run, monkeypatch, json_out):
    from pathlib import Path
    from connectonion.rem.service import subscriptions
    root, init, _ = first_run
    for folder in ('.codex/sessions', '.claude/projects'):
        (Path.home() / folder).mkdir(parents=True)
    walked = []
    monkeypatch.setattr('connectonion.rem.scan.source_files', lambda sub: walked.append(sub) or [])
    result = init('--no-investigate', '--no-start', *(['--json'] if json_out else []))
    assert result.exit_code == 0, result.output
    text = Text.from_ansi(result.output).plain
    assert 'waiting for approval; not scanned' in text
    assert 'codex' in text and 'claude-code' in text
    assert f'co rem --root {root} init --yes' in text
    assert walked == []
    assert not (root / '.state/consent.json').exists()
    assert not subscriptions(root)['codex']['consented']


def test_init_yes_records_existing_consent_before_mapping(first_run, monkeypatch):
    from connectonion.rem.files import read_json, state_path
    from connectonion.rem.map import build_map
    from connectonion.rem.service import subscriptions
    root, init, _ = first_run
    mapped = []

    def checked_map(root, sources, clients, **kwargs):
        assert read_json(state_path(root, 'consent.json'), {})['summary']
        assert sources['codex']['consented'] and sources['claude-code']['consented']
        assert subscriptions(root)['codex']['consented']
        mapped.append(True)
        return build_map(root, sources, clients, **kwargs)

    monkeypatch.setattr('connectonion.rem.map.build_map', checked_map)
    result = init('--yes', '--no-investigate', '--no-start')
    assert result.exit_code == 0, result.output
    assert mapped == [True]


def test_interactive_init_prompts_once_with_selected_mailboxes(first_run, monkeypatch):
    import sys
    from types import SimpleNamespace
    from connectonion.cli.commands import rem_commands
    from connectonion.rem.service import subscribe_read_mail, summary_fingerprint
    root, init, _ = first_run
    summaries, prompts, installed = [], [], []
    start_consent = rem_commands._start_consent

    def consent(ctx, summary, **kwargs):
        monkeypatch.setattr(sys.stdin, 'isatty', lambda: True)
        summaries.append(summary)
        return start_consent(ctx, summary, **kwargs)

    monkeypatch.setattr(rem_commands, '_start_consent', consent)
    monkeypatch.setattr('typer.confirm', lambda *args, **kwargs: prompts.append(args) or True)
    monkeypatch.setattr('connectonion.rem.schedule.default_scheduler', lambda *args, **kwargs: SimpleNamespace(
        install=lambda root, config: installed.append(root) or {'scheduler': 'fake'}))
    result = init('--no-investigate')
    assert result.exit_code == 0, result.output
    assert len(prompts) == 1
    assert len(summaries) == 1
    assert summaries[0]['sources']['gmail']['state'].startswith('will be read')
    assert installed == [root]
    fingerprint = summary_fingerprint(root)
    assert subscribe_read_mail(root, ['gmail']) == []
    assert summary_fingerprint(root) == fingerprint


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


def test_a_terminal_sees_a_bar_per_stage_and_each_finished_stage_once(monkeypatch):
    """#1996: 90 days is thirteen seven-day windows, so listing mail is a bar that fills;
    each stage's finished line stays, once, above the next stage's bar."""
    from connectonion.cli.commands.rem_output import StageProgress
    monkeypatch.setenv("TERM", "xterm")  # A fake TTY must simulate a terminal that supports live redraws.

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


def test_a_model_turn_is_a_spinner_with_its_time_in_a_terminal_and_lines_elsewhere(capsys, monkeypatch):
    from connectonion.cli.commands.rem_output import Turn
    monkeypatch.setenv("TERM", "xterm")

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
    mine = [call for call in calls if call["record"] == owner_record(root)]
    # Quick first, so a page is there in minutes; then the whole page alongside
    # the others (owner, 2026-10-01: the full pass alone was refused in two of
    # seven real first runs and nearly empty in a third).
    assert [call["quick"] for call in mine] == [True, False]
    assert calls[0]["record"] == owner_record(root)
    assert all(call["days"] == 5 and call["sent_only"] is True for call in mine)
    assert "me@example.org" in mine[0]["handles"]
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
    tail = result.output.rstrip().splitlines()[-6:]
    # Three counterparties; a sending address alone does not establish an owned company.
    assert tail[0] == "Your notebook: 4 people, 3 organisations, 0 projects and 0 skills."
    assert tail[1] == "Written this run: your page, 1 person and 1 organisation page."
    assert tail[2].startswith("Agent sessions: 0 imported, 0 updated, 0 unchanged;")
    assert tail[3].startswith("Your page: ") and tail[3].endswith(".md")
    assert tail[4].startswith("Background upkeep: Background upkeep needs approval.")
    assert f"co rem --root {root} start --yes" in tail[4]
    assert tail[5] == f"Next: co rem --root {root} open"


@pytest.mark.parametrize("ready", [True, False])
def test_rem_session_init_summarises_only_when_runner_ready(first_run, monkeypatch, ready):
    root, init, _ = first_run
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("", "") if ready else ("not installed", "install"))
    calls = []
    report = {"summarised": 1, "failed": 0, "batches": 1, "dropped_quotes": 0}
    monkeypatch.setattr("connectonion.rem.sessions.summarise_sessions",
                        lambda root, **kw: calls.append((root, kw)) or report)
    result = init("--no-investigate", "--no-start", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert "sessions" in data
    assert ("sessions_summary" in data) is ready
    assert len(calls) == int(ready)
    if ready:
        assert data["sessions_summary"] == report and calls[0][1]["limit"] == 40


def test_init_names_pages_that_are_probably_one_person_with_the_merge_that_joins_them(tmp_path):
    """#2349: a real first run gave Corin two pages and Zia Tanaka a second under 子亚;
    nothing said so, and `co rem merge` was there to join them."""
    from connectonion.cli.commands.rem_commands import _first_tidy, _init_done
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/zi.md", "子亚", ["zia@openonion.ai"], email="zia@openonion.ai")
    notebook.stub_person("people/zia.md", "Zia Tanaka", ["zia@openonion.ai"], email="zia@openonion.ai")
    said = []
    result = _first_tidy(tmp_path, said.append)
    assert result["pairs"] == [{"kept": "people/zi.md", "other": "people/zia.md",
                                "why": "both list zia@openonion.ai"}]

    class Ctx:
        obj = {"root": tmp_path, "json": False}
    text = _init_done(Ctx(), {"tidy": result})
    assert "Possibly one person (check, then merge): 子亚 and Zia Tanaka, both list zia@openonion.ai" in text
    assert f"co rem --root {tmp_path} merge people/zi.md people/zia.md" in text


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


def test_non_terminal_still_investigates_by_default(first_run, monkeypatch):
    monkeypatch.setattr("connectonion.cli.commands.rem_commands._interactive", lambda: False)
    root, init, calls = first_run
    result = init("--days", "5")
    assert result.exit_code == 0, result.output
    assert calls[0]["record"] == owner_record(root)
    assert [call["quick"] for call in calls if call["record"] == owner_record(root)] == [True, False]


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
    assert all(call["record"] != owner_record(root) for call in calls)
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
    assert (root / "logs/people-map.md").is_file()


# ------------------------------------------------------- runner preflight


def test_runner_preflight_checks_path_and_sign_in_without_a_model(tmp_path, monkeypatch):
    import importlib

    from connectonion.rem import runner as rem_runner
    from connectonion.rem.config import default_config

    # The package exports a `codex` function that shadows the module's name.
    codex = importlib.import_module("connectonion.useful_tools.codex")
    config = {**default_config(), "runner": "codex", "model": "gpt-6-luna"}
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


def test_init_recovers_older_messages_for_a_newly_mapped_project(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from connectonion.rem.config import prepare
    from connectonion.rem.map import build_map
    from connectonion.rem.project_material import extract, stored
    from connectonion.cli.commands.rem_commands import _first_project_rows
    root = tmp_path / 'rem'
    prepare(root)
    when = datetime.now(timezone.utc) - timedelta(days=30)
    folder = str(tmp_path / 'older-project')
    message = {'source': 'codex:old:100', 'tool': 'codex', 'timestamp': when.isoformat(),
               'cwd': folder, 'text': 'The release needs a migration check before publishing.'}
    monkeypatch.setattr('connectonion.rem.project_material.session_messages',
                        lambda subs, *, since, **kw: ([message] if since < when else [],
                                                     {'files': 1, 'harness': 0, 'unfamiliar': 0, 'excluded': {}}))
    monkeypatch.setattr('connectonion.rem.service.subscriptions', lambda root: {})
    extract(root, {}, create_pages=False)
    monkeypatch.setattr('connectonion.rem.map.scan_projects', lambda *a, **kw: [
        {'path': folder, 'repo': '', 'origin': '', 'sessions': 3,
         'first': when.date().isoformat(), 'last': when.date().isoformat()}])
    report = build_map(root, {}, {}, skill_directories=[])
    record = report['projects'][0]['record']
    rows = _first_project_rows(root, None)
    assert [row['record'] for row in rows] == [record]
    assert stored(root, record) == [message]
    _first_project_rows(root, None)
    assert stored(root, record) == [message]


def test_init_investigates_readable_project_files_when_typed_messages_are_missing(tmp_path, monkeypatch):
    from connectonion.rem.config import prepare, default_config
    from connectonion.rem.files import Notebook
    from connectonion.cli.commands.rem_commands import _first_project_rows, _project_jobs
    root = tmp_path / 'rem'
    prepare(root)
    folder = tmp_path / 'library'
    folder.mkdir()
    (folder / 'README.md').write_text('A local library awaiting its first release.')
    notebook = Notebook(root)
    notebook.stub_project('projects/library.md', 'Library', [str(folder)], sessions=1)
    notebook.stub_project('projects/gone.md', 'Gone', [str(tmp_path / 'gone')], sessions=1)
    monkeypatch.setattr('connectonion.rem.project_material.extract', lambda *a, **kw: {})
    calls = []
    monkeypatch.setattr('connectonion.cli.commands.rem_commands._investigate_page',
                        lambda root, nb, record, **kw: calls.append(record))
    rows = _first_project_rows(root, None)
    assert [row['record'] for row in rows] == ['projects/library.md']
    assert rows[0]['mode'] == 'full' and rows[0]['new_messages'] == 0
    _project_jobs(root, default_config(), rows)[0]['run']()
    assert calls == ['projects/library.md']


@pytest.fixture
def projects(first_run, monkeypatch):
    """Two projects active this fortnight and one older, with a spy where the model would write."""
    rows = [{"record": f"projects/{name}.md", "mode": "first", "last_activity": "2026-09-29T00:00:00Z",
             "recent": recent, "new_messages": 4, "chars": 2000, "left_out": 0}
            for name, recent in (("alpha", True), ("beta", True), ("old", False))]
    written = []
    monkeypatch.setattr("connectonion.rem.project_material.extract",
                        lambda root, subs, **kw: {"created": [], "filed_rows": [], "pages": []})
    monkeypatch.setattr("connectonion.rem.project_pages.queue",
                        lambda root, **kw: [row for row in rows if row["record"] not in written])

    def write_page(root, record, **kw):
        written.append(record)
        return {"record": record, "changed": [record]}

    monkeypatch.setattr("connectonion.rem.project_pages.write_page", write_page)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {"unknown": "no meter in tests"})
    return first_run, written


def test_after_me_all_queued_projects_are_written_one_line_each(projects):
    (root, init, calls), written = projects
    result = init()
    assert result.exit_code == 0, result.output
    assert calls[0]["record"] == owner_record(root)  # me first, then the people
    assert sorted(written) == ["projects/alpha.md", "projects/beta.md", "projects/old.md"]
    text = Text.from_ansi(result.output).plain
    # One total before the first page (#2008), for all selected pages.
    assert text.count("billed input tokens") == 1 and "Ctrl-C" in text
    assert "projects/old.md: written" in text


def test_refused_first_run_page_names_its_retry_and_keeps_schedule_off(projects, monkeypatch):
    from connectonion.rem.runner import RunFailed

    (root, init, _), _written = projects

    def write_page(root, record, **kw):
        if record == "projects/alpha.md":
            raise RunFailed("Candidate rejected; cited-claim audit did not pass")
        return {"record": record, "changed": [record]}

    monkeypatch.setattr("connectonion.rem.project_pages.write_page", write_page)
    result = init("--json", "--yes")
    assert result.exit_code == 1, result.output
    data = json.loads(result.stdout)
    assert data["data"]["background"]["started"] is False
    assert data["next"].endswith("investigate projects/alpha.md --retry-refused")


def test_a_first_run_with_pages_not_written_says_how_many_instead_of_an_empty_error(projects, monkeypatch):
    """1.9.2b2 trial: 23 pages were not written and the run ended on a bare "Error: "."""
    from connectonion.rem.runner import RunFailed

    (root, init, _), _written = projects

    def write_page(root, record, **kw):
        if record == "projects/alpha.md":
            raise RunFailed("Candidate rejected; cited-claim audit did not pass")
        return {"record": record, "changed": [record]}

    monkeypatch.setattr("connectonion.rem.project_pages.write_page", write_page)
    lines = Text.from_ansi(init("--yes").output).plain.splitlines()
    assert "Error:" not in [line.rstrip() for line in lines], lines[-8:]
    assert "Error: 1 page was not written this run; each is named above with why." in lines


def test_projects_follow_explicit_skip_and_runner_readiness(projects, monkeypatch):
    (root, init, calls), written = projects
    assert init("--no-investigate").exit_code == 0
    data = json.loads(init("--json").stdout)["data"]
    assert data["project_pages"]["started"]
    monkeypatch.setattr("connectonion.cli.commands.rem_commands._interactive", lambda: False)
    assert init().exit_code == 0
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("Codex is not signed in", "codex login"))
    missing = init("--investigate")
    assert Text.from_ansi(missing.output).plain.count("Codex is not signed in") == 1
    assert sorted(written) == ["projects/alpha.md", "projects/beta.md", "projects/old.md"]


def test_json_with_investigate_writes_projects_and_reports_them(projects):
    (root, init, calls), written = projects
    result = init("--json", "--investigate")
    assert result.exit_code == 0, result.output
    pages = json.loads(result.stdout)["data"]["project_pages"]
    assert pages["started"] and sorted(row["page"] for row in pages["pages"]) == sorted(written) == [
        "projects/alpha.md", "projects/beta.md", "projects/old.md"]


def test_the_weekly_floor_does_not_stop_init_projects(projects, monkeypatch):
    (root, init, calls), written = projects
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {
        "used_percent": 90, "window_minutes": 10080, "resets_at": 4102444800, "plan": "plus"})
    result = init()
    assert result.exit_code == 0, result.output
    assert len(written) == 3
    assert "No REM page or weekly quota cap stops this first run" in Text.from_ansi(result.output).plain


# ------------------------------------------- the people you write to, after me


@pytest.fixture
def people(projects, monkeypatch):
    """Five people in the queue, most-written-to first, and a spy where each person's turn would be."""
    (root, init, calls), written = projects
    rows = [{"record": f"people/p{n}.md", "mode": "full", "days": 150, "last_activity": "2026-09-29T00:00:00Z",
             "recent": n < 4, "mails": 10 - n, "sent": 3, "received": 3, "last_investigated": None}
            for n in range(5)]
    people_written = []
    monkeypatch.setattr("connectonion.rem.people_pages.queue",
                        lambda root, **kw: [row for row in rows if row["record"] not in people_written])

    def investigate_person(root, row, **kw):
        people_written.append(row["record"])
        return {"record": row["record"], "changed": [row["record"]]}

    monkeypatch.setattr("connectonion.rem.people_pages.investigate_person", investigate_person)
    return root, init, calls, people_written, written


def test_after_me_the_people_you_wrote_to_and_projects_four_at_a_time(people):
    """Owner, 2026-09-30: the first run shows the people around you, not only
    you; 2026-10-01: all of the last fortnight's, several at once."""
    root, init, calls, people_written, projects_written = people
    result = init()
    assert result.exit_code == 0, result.output
    assert calls[0]["record"] == owner_record(root)  # then the organisations, alongside
    assert sorted(people_written) == [f"people/p{n}.md" for n in range(5)]
    assert sorted(projects_written) == ["projects/alpha.md", "projects/beta.md", "projects/old.md"]
    text = Text.from_ansi(result.output).plain
    assert "up to two years of evidence each" in text
    assert "16 at a time" in text and "No REM page or weekly quota cap stops this first run" in text
    assert "People 5/5" in text and "Projects 3/3" in text
    assert "Written this run: your page, 5 people" in text and "3 project pages" in text


def test_init_uses_the_notebooks_workers_for_the_page_queue(people, monkeypatch):
    from connectonion.cli.commands import rem_commands
    from connectonion.rem.config import set_config

    root, init, calls, people_written, projects_written = people
    set_config(root, ["limits.workers", "3"])
    parallel = rem_commands._in_parallel
    seen = []

    def run(jobs, *, workers, gate, done):
        seen.append(workers)
        return parallel(jobs, workers=workers, gate=gate, done=done)

    monkeypatch.setattr(rem_commands, "_in_parallel", run)
    result = init("--no-start")
    assert result.exit_code == 0, result.output
    assert seen == [3]
    assert len(people_written) == 5 and len(projects_written) == 3
    assert "up to 3 at a time" in result.output and "with up to 3 workers" in result.output


def test_the_first_run_finishes_selected_pages_past_target(people, monkeypatch):
    """The configured target is advisory; the cohort finishes below the safety floor."""
    from connectonion.rem.config import default_config
    root, init, calls, people_written, projects_written = people
    meter = {"used_percent": 10, "window_minutes": 10080, "resets_at": 4102444800, "plan": "plus"}
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: dict(meter))

    def one_person_costs_the_whole_budget(root, row, **kw):
        people_written.append(row["record"])
        meter["used_percent"] += default_config()["limits"]["investigation_quota_points"] + 1
        return {"record": row["record"], "changed": [row["record"]]}

    monkeypatch.setattr("connectonion.rem.people_pages.investigate_person", one_person_costs_the_whole_budget)
    result = init("--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert len(people_written) == 5 and len(projects_written) == 3
    assert data["people_pages"]["left"] == 0
    assert data["org_pages"]["started"] is True


def test_first_run_does_not_stop_at_the_weekly_floor(people, monkeypatch):
    root, init, _, people_written, projects_written = people
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {"used_percent": 100})
    result = init("--json")
    assert result.exit_code == 0, result.output
    assert len(people_written) == 5 and len(projects_written) == 3
    assert json.loads(result.stdout)["data"]["people_pages"]["left"] == 0


def test_ctrl_c_during_people_keeps_the_pages_and_names_the_rest(people, monkeypatch):
    root, init, calls, people_written, _ = people

    def interrupted(root, row, **kw):
        if row["record"] == "people/p2.md":
            raise KeyboardInterrupt
        people_written.append(row["record"])
        return {"record": row["record"], "changed": [row["record"]]}

    monkeypatch.setattr("connectonion.rem.people_pages.investigate_person", interrupted)
    result = init()
    assert result.exit_code == 130
    assert "people/p2.md" not in people_written
    text = Text.from_ansi(result.output).plain
    assert f"--root {root} investigate all" in text




# ------------------------------------------- what the first run spends (#2008)


def test_the_first_run_writes_every_page_and_a_flag_caps_a_kind(people, monkeypatch):
    """The eligible queue runs by default; --first-* caps a kind (0 for none)."""
    root, init, calls, people_written, projects_written = people
    rows = [{"record": f"projects/p{n}.md", "mode": "first", "last_activity": "2026-09-29T00:00:00Z",
             "recent": True, "new_messages": 1, "chars": 100, "left_out": 0} for n in range(5)]
    monkeypatch.setattr("connectonion.rem.project_pages.queue",
                        lambda root, **kw: [row for row in rows if row["record"] not in projects_written])
    assert init().exit_code == 0
    assert len(projects_written) == 5 and len(people_written) == 5
    projects_written.clear()
    people_written.clear()
    result = init("--first-projects", "3", "--first-people", "1", "--first-orgs", "0", "--json", "--investigate")
    assert result.exit_code == 0, result.output
    assert len(projects_written) == 3 and people_written == ["people/p0.md"]
    plan = json.loads(result.stdout)["data"]["first_run"]
    assert plan["counts"] == {"owner": 1, "person": 1, "project": 3, "org": 0}


def test_all_history_estimate_maps_without_model_turns_or_body_archive(first_run):
    root, init, calls = first_run
    result = init("--investigate-all", "--estimate-only", "--first-orgs", "0", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert data["all_history"] and data["estimate_only"]
    assert data["first_run"]["counts"]["owner"] == 1
    assert data["first_run"]["counts"]["person"] >= 1
    assert calls == []
    assert not (root / ".state/mail/archive.json").exists()
    assert "all available history since 1970" in (root / ".state/source-inventory.md").read_text()


def test_all_history_estimate_marks_a_failed_mailbox_as_a_lower_bound(first_run, monkeypatch):
    root, init, calls = first_run
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    class Down:
        def my_addresses(self): raise TimeoutError("mailbox unavailable")

    monkeypatch.setattr("connectonion.rem.service.mail_client", lambda kind, **kw: Down())
    result = init("--all-history", "--investigate-all", "--estimate-only", "--name", "Ada Owner", "--json")
    assert result.exit_code == 1, result.output
    data = json.loads(result.stdout)["data"]
    assert data["estimate_only"] and data["first_run"]["source_coverage"] == "incomplete"
    assert data["errors"][0]["stage"] == "account"
    assert calls == []
    assert not (root / ".state/mail/archive.json").exists()


def test_the_estimate_is_the_median_of_this_notebooks_own_runs():
    from connectonion.rem import first_run as fr
    from connectonion.rem.config import default_config

    assert default_config()["limits"]["workers"] == 16

    def run(phase, record, tokens, seconds, outcome="completed"):
        return {"phase": phase, "record": record, "outcome": outcome, "seconds": seconds,
                "usage": {"input_tokens": tokens}}

    runs = [run("projects write", "projects/a.md", 614_000, 240), run("projects write", "projects/b.md", 922_000, 300),
            run("projects write", "projects/c.md", 700_000, 270),
            run("projects write", "projects/d.md", 9_000_000, 900, outcome="interrupted"),
            run("investigate", "orgs/x.md", 5_000_000, 999)]
    assert fr.per_page(runs, "project") == {"input_tokens": 700_000, "seconds": 270, "measured": 3}
    assert fr.per_page(runs, "person") == {**fr.DEFAULTS["person"], "measured": 0}
    total = fr.plan(runs, owner=False, people=0, projects=2, workers=1)
    assert total["input_tokens"] == 1_400_000 and total["minutes"] == 9
    assert fr.plan(runs, owner=False, people=0, projects=20, workers=10)["minutes"] == 9  # wall clock, shared
    owner_only = fr.plan(runs, owner=True, people=0, projects=0, workers=10)
    assert owner_only["input_tokens"] == 2 * fr.DEFAULTS["owner"]["input_tokens"]
    assert owner_only["minutes"] == 71  # quick and full are two turns, not one
    line = fr.announce(total, "on your Codex plan")
    assert line == ("About 2 pages (2 projects), ~1.4M billed input tokens on your Codex plan, ~9 minutes "
                    "(an estimate from this notebook's own runs).")
    mixed = fr.announce(fr.plan(runs, owner=True, people=1, projects=1,
                                workers=default_config()["limits"]["workers"]), "on your Codex plan")
    assert "About 3 pages (your page, 1 person and 1 project)" in mixed and "measured defaults otherwise" in mixed


def test_a_fresh_notebook_estimate_matches_the_measured_first_run():
    """1.9.2b1 announced ~70 minutes and ~196M input for 280 pages; it ran
    129 minutes of pages and billed 439M. The defaults were from an
    interrupted sample: the owner's turns took 20 minutes, not 7, an
    organisation 8 minutes, not 1.5, and 84 people needed 141 runs with their
    second pass. 1.9.2b3's 48 workers announced ~30 and ran 126: the model's
    throughput, not the worker count, sets the pace."""
    from connectonion.rem import first_run as fr

    b1 = dict(owner=True, people=84, projects=20, orgs=27, skills=148)
    from connectonion.rem.config import default_config
    total = fr.plan([], **b1, workers=default_config()["limits"]["workers"])
    # Since 2026-10-20 the defaults never announce less than a measured run took:
    # pages now read in rounds and are deepened, so they cost more than b1's did.
    assert 129 <= total["minutes"] <= 1.35 * 129
    assert 439_000_000 <= total["input_tokens"] <= 1.35 * 439_000_000
    assert fr.plan([], **b1, workers=48)["minutes"] == total["minutes"]


def test_the_estimate_matches_the_2026_10_20_release_check():
    """It announced ~42 minutes and ~50M input tokens for your page, ten people,
    three projects, two organisations and a skill; the run took 82 minutes of
    pages after an 11.5-minute quick page, and 102M input tokens."""
    from connectonion.rem import first_run as fr
    total = fr.plan([], owner=True, people=10, projects=3, orgs=2, skills=1, workers=16)
    assert 90 <= total["minutes"] <= 105
    assert 95_000_000 <= total["input_tokens"] <= 110_000_000


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
    assert "pages written before the stop" in text and "and kept." in text
    assert f"Next: co rem --root {root} investigate all" in text


# ------------------------------------------- several pages at once (owner, 2026-10-01)


def test_the_first_run_writes_people_and_projects_several_at_once(people, monkeypatch):
    """A person takes minutes, most of it waiting on the mailbox and the model,
    and the owner judged the cost small: the first run writes four at a time."""
    import threading
    root, init, calls, people_written, projects_written = people
    together = threading.Event()
    lock = threading.Lock()
    started = []

    def slow_person(root, row, **kw):
        with lock:
            started.append(row["record"])
            if len(started) == 4:
                together.set()
        assert together.wait(10)  # four pages must overlap before any completes
        people_written.append(row["record"])
        return {"record": row["record"], "changed": [row["record"]]}

    monkeypatch.setattr("connectonion.rem.people_pages.investigate_person", slow_person)
    result = init("--json", "--investigate")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert [row["outcome"] for row in data["people_pages"]["pages"]][:4] == ["accepted"] * 4


def test_the_first_run_covers_eligible_correspondents_including_older(people):
    root, init, calls, people_written, projects_written = people
    result = init()
    assert result.exit_code == 0, result.output
    assert sorted(people_written) == [f"people/p{n}.md" for n in range(5)]
    assert sorted(projects_written) == ["projects/alpha.md", "projects/beta.md", "projects/old.md"]


def test_first_run_uses_full_requested_window_and_all_pending_orgs(tmp_path, monkeypatch):
    from connectonion.cli.commands.rem_commands import _first_org_rows, _first_people_rows

    people = [{"record": f"people/p{n}.md"} for n in range(20)]
    windows = []

    def queue(root, *, recent_days):
        windows.append(recent_days)
        return people

    monkeypatch.setattr("connectonion.rem.people_pages.queue", queue)
    assert _first_people_rows(tmp_path, None, 90) == people
    assert _first_people_rows(tmp_path, 3, 90) == people[:3]
    assert windows == [90, 90]

    orgs = [{"path": "orgs/linked.md", "recent": False},
            {"path": "orgs/unlinked.md", "recent": False}]
    monkeypatch.setattr("connectonion.rem.queue.order", lambda root, category: orgs)
    assert _first_org_rows(tmp_path, None) == orgs
    assert _first_org_rows(tmp_path, 1) == orgs[:1]


def test_marking_people_investigated_at_once_loses_none(tmp_path, monkeypatch):
    """Four people finishing together each read investigated.json, add
    themselves and write it back; without the lock the last write wins."""
    import threading
    import time
    from datetime import datetime, timezone
    from connectonion.rem import people_pages
    real = people_pages.read_json

    def slow_read(path, default):
        value = real(path, default)
        time.sleep(0.05)  # the gap another thread writes into
        return value

    monkeypatch.setattr(people_pages, "read_json", slow_read)
    when = datetime(2026, 10, 1, tzinfo=timezone.utc)
    threads = [threading.Thread(target=people_pages.mark_investigated, args=(tmp_path, f"people/p{n}.md", when))
               for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    done = json.loads((tmp_path / ".state/people/investigated.json").read_text())
    assert sorted(done) == [f"people/p{n}.md" for n in range(4)]


def test_a_finished_investigation_waits_for_the_lock_instead_of_losing_the_page(tmp_path):
    """Two pages finishing a second apart: the second used to raise "co rem is
    busy" after its model turn had been paid for."""
    import threading
    from connectonion.rem.files import Notebook, maintenance_lock
    from connectonion.rem.investigate import record_result
    notebook = Notebook(tmp_path)
    notebook.write("people/p0.md", "# P0\n\nInvestigation: mapped 2026-09-30 · not investigated yet\n")
    held, release = threading.Event(), threading.Event()

    def hold():
        with maintenance_lock(tmp_path):
            held.set()
            release.wait(5)

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait(5)
    threading.Timer(0.5, release.set).start()
    record_result(tmp_path, notebook, "people/p0.md", [], ["outlook"])
    holder.join()
    assert "investigated" in notebook.read("people/p0.md")


def test_the_first_run_selects_older_projects_and_related_organisations(people):
    """Older eligible pages remain in init after the recent pages."""
    root, init, calls, people_written, projects_written = people
    result = init()
    assert result.exit_code == 0, result.output
    assert "projects/old.md" in projects_written
    assert any(call["record"].startswith("orgs/") for call in calls)


def test_a_refused_owner_page_does_not_cost_the_rest_of_the_first_run(people, monkeypatch):
    """A real first run (2026-10-01): the owner's page was refused after two
    minutes and init stopped there, with 240 people, project and organisation
    pages never started. The owner's page is one page among them."""
    from connectonion.rem.runner import RunFailed
    root, init, calls, people_written, projects_written = people

    def refused(root, **kw):
        raise RunFailed("Candidate rejected: page cites only the page itself")

    monkeypatch.setattr("connectonion.cli.commands.rem_commands._investigate_me", refused)
    result = init("--json", "--investigate")
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["data"]["investigation"] == "failed"
    assert payload["next"].endswith("investigate me")
    assert sorted(people_written) == [f"people/p{n}.md" for n in range(5)]
    assert "projects/alpha.md" in projects_written


def test_one_unreadable_mail_body_does_not_skip_the_first_run(first_run, monkeypatch):
    """A real first run (2026-10-01): 1 of 1,880 bodies timed out, the map was
    called partial, and init told the owner to check mailbox access and
    investigated nothing. The archive is a cache; a missing body is a note."""
    import requests
    real = Mail.get_email_body

    def one_times_out(self, message_id):
        if message_id.endswith("-self2"):
            raise requests.exceptions.ReadTimeout("read timed out")
        return real(self, message_id)

    monkeypatch.setattr(Mail, "get_email_body", one_times_out)
    root, init, calls = first_run
    result = init()
    assert result.exit_code == 0, result.output
    assert calls and calls[0]["record"] == owner_record(root)
    text = Text.from_ansi(result.output).plain
    assert "could not be saved" in text and "co auth status" not in text


def test_a_refused_full_owner_page_keeps_the_quick_first_pass(first_run, monkeypatch):
    """The full pass runs after the quick one; refused, the quick page stays."""
    from connectonion.rem.runner import RunFailed
    tried = []

    def full_refused(root, days=None, quick=False, **kw):
        tried.append(quick)
        if not quick:
            raise RunFailed("Candidate rejected: page cites only the page itself")
        return {"record": "people/me.md"}, "people/me.md"

    monkeypatch.setattr("connectonion.cli.commands.rem_commands._investigate_me", full_refused)
    root, init, _ = first_run
    result = init("--json", "--investigate")
    assert result.exit_code == 1, result.output
    assert tried == [True, False]
    data = json.loads(result.stdout)["data"]
    assert data["investigate_me"]["outcome"] == "completed"
    assert data["owner_full"]["pages"][0]["outcome"] == "refused"
    assert data["background"]["started"] is False


def test_the_first_run_ends_by_drawing_decisions_and_principles_from_its_pages(tmp_path, monkeypatch):
    """The owner (2026-10-08): init should leave decisions and principles too."""
    from connectonion.cli.commands import rem_commands
    from connectonion.rem.runner import RunFailed
    calls, said = [], []
    monkeypatch.setattr("connectonion.rem.runner.run_stage", lambda notebook, items, config, stage: calls.append(stage)
                        or {"changed": ["decisions/launchd-not-cron.md", "principles/test-before-you-ship.md",
                                        "people/x.md"], "usage": {"input_tokens": 9}})
    wrote = {"people_pages": {"pages": [{"outcome": "accepted"}]}}
    out = rem_commands._first_abstract(tmp_path, {}, said.append, wrote)
    assert calls == ["abstract"] and out["pages"] == ["decisions/launchd-not-cron.md", "principles/test-before-you-ship.md"]
    assert rem_commands._first_abstract(tmp_path, {}, said.append, {"people_pages": {"pages": []}}) == {"started": False}
    assert calls == ["abstract"]  # nothing written, nothing to lift

    def refuse(*a, **k):
        raise RunFailed("model denied access", {"input_tokens": 1})
    monkeypatch.setattr("connectonion.rem.runner.run_stage", refuse)
    failed = rem_commands._first_abstract(tmp_path, {}, said.append, wrote)
    assert failed["outcome"] == "failed" and "co rem abstract" in said[-1]


def test_people_whose_backfill_found_older_mail_are_deepened_on_the_parts_before_the_window(tmp_path, monkeypatch):
    """The owner (2026-10-08): read the mapped window first, fetch the rest of two
    years in parallel, then deepen. 2026-10-09: within a 45-minute first run, so
    the deepen pass reads three parts, the ones before the window the first pass read."""
    from concurrent.futures import Future
    from connectonion.cli.commands import rem_commands

    def done(value):
        future = Future()
        future.set_result(value)
        return future

    ran = []
    monkeypatch.setattr(rem_commands, "_people_jobs", lambda root, rows: [
        {"kind": "people", "record": row["record"], "mode": "full", "row": row, "run": lambda row=row: ran.append(row)}
        for row in rows])
    row = {"record": "people/a.md", "mode": "full", "days": 730}
    found = rem_commands._deepen_job(tmp_path, row, done(12), "2026-04-12")
    empty = rem_commands._deepen_job(tmp_path, {**row, "record": "people/b.md"}, done(0), "2026-04-12")
    found["run"](), empty["run"]()
    assert [r["record"] for r in ran] == ["people/a.md"]   # b's backfill found nothing older
    assert ran[0] == {**row, "rounds": rem_commands.FIRST_RUN_ROUNDS, "read_before": "2026-04-12"}
    assert found["kind"] == "deepen" and found["older"]() and not empty["older"]()


def test_a_finished_page_can_queue_its_follow_up_behind_the_pages_still_waiting():
    """A person's deepen starts once every first-pass page has started, not finished (rc1 idled 80 minutes)."""
    from connectonion.cli.commands.rem_commands import _in_parallel
    order = []
    follow = {"record": "people/a.md#deepen", "mode": "full", "run": lambda: order.append("a-deepen")}
    jobs = [{"record": name, "mode": "full", "run": lambda name=name: order.append(name)} for name in ("a", "b")]
    outcomes, _ = _in_parallel(jobs, workers=1, gate=lambda: "",
                               done=lambda job, outcome: [follow] if job["record"] == "a" else [])
    assert order == ["a", "b", "a-deepen"] and len(outcomes) == 3


def test_a_failed_page_is_tried_once_more_at_the_end_of_the_queue():
    """1.9.2b2 lost three pages to a Codex routing timeout, an interrupted turn and a
    dropped Gmail connection, each of which a second try would have survived."""
    from connectonion.rem.files import RemError
    from connectonion.cli.commands.rem_commands import _in_parallel
    tries = []

    def flaky(name, failures):
        def run():
            tries.append(name)
            if tries.count(name) <= failures:
                raise RemError(f"{name}: workspace routing discovery timed out")
        return {"record": name, "mode": "full", "run": run}

    def refused():
        tries.append("r")
        raise RemError("Candidate rejected: one bad citation")

    jobs = [flaky("a", 1), flaky("b", 0), flaky("c", 5), {"record": "r", "mode": "full", "run": refused}]
    outcomes, _ = _in_parallel(jobs, workers=1, gate=lambda: "", done=lambda job, outcome: [])
    assert tries == ["a", "b", "c", "r", "a", "c"]
    assert {o["page"]: o["outcome"] for _, o in outcomes} == {"a": "accepted", "b": "accepted", "c": "failed",
                                                             "r": "refused"}


def test_a_deepen_with_nothing_older_is_not_a_failure_and_is_not_retried():
    """1.9.2b3 trial: three people with no older mail printed 'deepened …: failed'
    and ran twice; nothing had failed."""
    from connectonion.rem.investigate import NothingNew
    from connectonion.cli.commands.rem_commands import _in_parallel
    tries = []

    def run():
        tries.append("briar")
        raise NothingNew("Nothing dated before 2026-04-13 for Briar. No model was called.")

    outcomes, _ = _in_parallel([{"record": "people/briar.md", "mode": "full", "run": run}], workers=1,
                               gate=lambda: "", done=lambda job, outcome: [])
    assert tries == ["briar"] and outcomes[0][1]["outcome"] == "nothing_new"


@pytest.mark.parametrize('flags', [
    ['--yes', '--no-start', '--estimate-only'],
    ['--yes', '--no-start', '--no-investigate'],
    ['--yes', '--no-start'],
])
def test_init_reads_sessions_in_the_map_without_spawning_a_warmer(first_run, monkeypatch, flags):
    from connectonion.rem import session_pass
    root, init, _ = first_run
    reads = []
    read = session_pass.read_sessions

    def shared(root, sources, **kwargs):
        reads.append(root)
        return read(root, sources, **kwargs)

    monkeypatch.setattr(session_pass, 'read_sessions', shared)
    monkeypatch.setattr('multiprocessing.get_context', lambda *a: pytest.fail('spawned a warmer'))
    result = init(*flags)
    assert result.exit_code == 0, result.output
    assert reads == [root]


def test_init_passes_the_maps_sessions_to_import(first_run, monkeypatch):
    from connectonion.rem import sessions
    root, init, _ = first_run
    received = []
    import_sessions = sessions.import_sessions

    def imported(root, **kwargs):
        received.append(kwargs.get('sessions'))
        return import_sessions(root, **kwargs)

    monkeypatch.setattr(sessions, 'import_sessions', imported)
    result = init('--yes', '--no-start')
    assert result.exit_code == 0, result.output
    assert len(received) == 1 and received[0] is not None


def test_init_translation_selects_only_listed_written_pages_without_daily_cap(tmp_path, monkeypatch):
    from connectonion.cli.commands.rem_commands import _first_translation
    from connectonion.rem.config import prepare, read_config, set_config
    from connectonion.rem.files import Notebook
    from connectonion.rem import translate
    from connectonion.rem.service import run_logs
    prepare(tmp_path)
    set_config(tmp_path, ['limits.translations_per_day', '1', 'limits.workers', '3'])
    book = Notebook(tmp_path)
    records = ['people/avery-lin.md', 'orgs/northgate-university.md', 'projects/draft.md',
               'skills/catalog/weekly-brief.md', 'decisions/format.md', 'principles/simple.md']
    for record in records:
        book.write(record, '# Invented page\n\nWritten findings.\n\nInvestigation: investigated 2026-10-21\n')
    book.stub_project('projects/mapped.md', 'Mapped', ['/work/mapped'])
    book.stub_person('people/mia-chen.md', 'Mia Chen', ['mia@example.com'])
    book.write('skills/catalog/mapped.md', '# Mapped skill\n\nInvestigation: not investigated yet\n')
    book.write('skills/catalog/zz-weekly-brief-copy.md', book.read('skills/catalog/weekly-brief.md'))
    book.write('skills/catalog/index.md', '# Skills\n')
    book.write('sessions/session.md', '# Session\n')
    calls, said = [], []
    monkeypatch.setattr(translate, 'translate', lambda root, page, language: calls.append((page, language)))
    report = _first_translation(tmp_path, read_config(tmp_path), said.append, language='zh')
    assert sorted(page for page, language in calls) == sorted(records)
    assert all(language == 'zh' for page, language in calls)
    assert report['translated'] == 6 and report['started']
    assert said == ['Translating 6 pages into zh…']
    [summary] = run_logs(tmp_path)
    assert summary['phase'] == 'init-translation' and 'usage' not in summary


@pytest.mark.parametrize('flags, language, reason', [
    ([], 'en', 'English-only'), (['--no-translate'], 'en,zh', '--no-translate'),
    (['--no-investigate'], 'en,zh', '--no-investigate'),
    (['--estimate-only'], 'en,zh', 'Estimate only'),
    ([], 'en,zh', 'Runner not ready')])
def test_init_reports_why_translation_is_skipped(first_run, monkeypatch, flags, language, reason):
    root, init, _ = first_run
    monkeypatch.setattr('connectonion.rem.translate.translate_pages', lambda *args, **kw: pytest.fail('translation started'))
    if reason == 'Runner not ready':
        monkeypatch.setattr('connectonion.rem.runner.ready', lambda config: ('runner unavailable', 'install runner'))
    result = init('--json', '--languages', language, '--no-start', *flags)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)['data']
    assert not data['translation']['started'] and reason in data['translation']['reason']
    assert data['languages']['languages'] == language.split(',') and data['languages']['from'].startswith('set')


def test_init_translates_secondary_chinese_after_tidy_and_abstract(first_run, monkeypatch):
    from connectonion.cli.commands import rem_commands
    from connectonion.rem.files import Notebook
    root, init, _ = first_run
    order = []

    def tidy(root, say):
        order.append('tidy')
        return {}

    def abstract(root, config, say, result):
        order.append('abstract')
        Notebook(root).write('decisions/format.md', '# Format\n\nUse Markdown.\n')
        return {}

    def translate_pages(root, language, records, **options):
        order.append('translate')
        assert language == 'zh' and 'decisions/format.md' in records
        assert options['workers'] == 16
        return {'language': language, 'pages': [], 'translated': len(records), 'cached': 0, 'failed': 0}

    monkeypatch.setattr(rem_commands, '_first_tidy', tidy)
    monkeypatch.setattr(rem_commands, '_first_abstract', abstract)
    monkeypatch.setattr('connectonion.rem.translate.translate_pages', translate_pages)
    result = init('--json', '--languages', 'en,zh', '--no-start')
    assert result.exit_code == 0, result.output
    assert order == ['tidy', 'abstract', 'translate']
    data = json.loads(result.stdout)['data']
    assert data['translation']['started'] and data['translation']['language'] == 'zh'
    assert data['first_run']['translation']['language'] == 'zh'


def test_init_language_line_precedes_spending_and_languages_are_validated_before_map(first_run, monkeypatch):
    root, init, _ = first_run
    result = init('--languages', 'zh,en', '--no-start', '--estimate-only')
    assert result.exit_code == 0, result.output
    text = Text.from_ansi(result.output).plain
    assert 'Languages: 中文, English (set with co rem config set languages).' in text
    assert 'Pages are written in English and translated into 中文.' in text
    assert f'To change: co rem --root {root} config set languages zh,en (current)' in text
    assert f'— or `co rem --root {root} config set languages en` for English only.' in text
    assert text.index('Languages:') < text.index('First run with')
    assert 'translation of the written pages into 中文/zh' in text
    monkeypatch.setattr('connectonion.rem.map.build_map', lambda *args, **kw: pytest.fail('map started'))
    invalid = init('--languages', '../zh')
    assert invalid.exit_code == 1 and 'language tags' in invalid.output


@pytest.mark.parametrize('languages', ['en', 'en-AU,en'])
def test_init_english_only_language_tip_shows_only_the_current_form(first_run, languages):
    root, init, _ = first_run
    result = init('--languages', languages, '--no-start', '--estimate-only')
    assert result.exit_code == 0, result.output
    text = Text.from_ansi(result.output).plain
    assert f'To change: co rem --root {root} config set languages {languages} (current)' in text
    assert 'for English only' not in text


def test_translation_estimate_uses_completed_local_medians_and_separate_worker_lanes():
    from connectonion.rem import first_run as fr
    counts = dict(owner=True, people=2, projects=1, orgs=1, skills=1, workers=2)
    plain = fr.plan([], **counts)
    default = fr.plan([], **counts, translation='zh')
    assert default['translation']['pages'] == 6
    assert default['input_tokens'] == plain['input_tokens'] + 6 * 90_000
    assert default['minutes'] == plain['minutes'] + 10  # 3 batches x 200 seconds, after investigations.
    runs = [{'phase': 'translate', 'outcome': outcome, 'seconds': seconds, 'usage': {'input_tokens': tokens}}
            for outcome, seconds, tokens in [('completed', 20, 74000), ('completed', 40, 80000), ('failed', 999, 999999)]]
    total = fr.plan(runs, **counts, translation='zh', abstract_pages=2)
    assert total['translation'] == {'language': 'zh', 'pages': 8, 'seconds': 30, 'input_tokens': 77000, 'measured': 2}
    assert total['input_tokens'] == plain['input_tokens'] + 8 * 77000
    assert total['minutes'] == plain['minutes'] + 2
    assert '8 translations into zh after the page queue' in fr.announce(total, 'on your plan')


def test_detected_languages_are_printed_without_promising_skipped_translations(first_run, monkeypatch):
    root, init, _ = first_run
    monkeypatch.setattr('connectonion.rem.languages.owner_languages', lambda root: {
        'languages': ['zh', 'en'], 'from': 'detected from your own mail and sessions', 'detected': ['zh', 'en']})
    result = init('--no-investigate', '--no-start')
    assert result.exit_code == 0, result.output
    assert 'Languages: 中文, English (detected from your sent mail and typed sessions).' in result.output
    assert 'Translation: Skipped by --no-investigate.' in result.output
    assert 'and translated into 中文' not in result.output


def test_init_translation_failure_keeps_other_pages_and_prints_one_failure_each(tmp_path, monkeypatch):
    from connectonion.cli.commands.rem_commands import _first_translation
    from connectonion.rem.config import prepare, read_config
    from connectonion.rem.files import Notebook, RemError
    from connectonion.rem.service import run_logs
    prepare(tmp_path)
    for record in ['people/avery-lin.md', 'people/mara-ostrowski.md']:
        Notebook(tmp_path).write(record, '# Invented page\n\nWritten findings.\n')

    def translate(root, record, language):
        if record == 'people/avery-lin.md':
            raise RemError('fixture translation refused')

    monkeypatch.setattr('connectonion.rem.translate.translate', translate)
    said = []
    report = _first_translation(tmp_path, read_config(tmp_path), said.append, language='zh')
    assert report['failed'] == report['translated'] == 1
    assert said == ['Translating 2 pages into zh…', 'people/avery-lin.md: failed: fixture translation refused']
    assert run_logs(tmp_path)[0]['outcome'] == 'partial'


def test_init_summary_reports_translated_pages_and_how_to_retry_failures():
    from types import SimpleNamespace
    from connectonion.cli.commands.rem_commands import _translation_line
    ctx = SimpleNamespace(obj={"json": False, "root": None, "default_root": True})
    report = {"started": True, "language": "zh", "pages": [{}, {}, {}], "translated": 1, "cached": 1, "failed": 1}
    line, = _translation_line(ctx, report)
    assert line.startswith("Translated into zh: 2 of 3 pages. 1 failed; retry with ")
    assert line.endswith("translate --all.")
    assert _translation_line(ctx, {"started": False, "reason": "Skipped by --no-translate."}) == []
