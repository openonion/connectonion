"""The daily round sends each page to its own investigator and keeps dead pages from starving it.

From the 2026-10-10..15 notebook: skill pages were investigated through a mail
search and came back nothing_found three days running, the day's three slots
went to pages with nothing to write from, the round called that
`no_page_fits_budget`, and orgs/connectonion-com and every refused page were
never tried again.
"""

from datetime import datetime, timedelta, timezone

import pytest

from connectonion.rem import daily
from connectonion.rem.config import prepare, read_config, set_config
from connectonion.rem.files import Notebook
from connectonion.rem.investigate import NothingFound
from connectonion.rem.refusals import refused_pages, remember_refusal


def no_change(root):
    return {"outcome": "no_change"}


@pytest.mark.parametrize("enabled,consented,unsubscribed", [
    (False, False, False), (True, False, False), (False, True, False),
    (True, True, True), (True, True, False),
])
def test_daily_mail_clients_require_an_approved_subscription(monkeypatch, enabled, consented, unsubscribed):
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: True)
    monkeypatch.setattr(daily, "mail_client", lambda kind, **kwargs: kind)
    sources = {"gmail": {"enabled": True, "consented": True},
               "outlook": {"enabled": enabled, "consented": consented, "unsubscribed": unsubscribed}}
    expected = {"gmail", "outlook"} if enabled and consented and not unsubscribed else {"gmail"}
    assert set(daily._clients(sources)) == expected


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
    set_config(root, ["schedule.timezone", "UTC"])
    notebook = Notebook(root)
    notebook.stub_skill("skills/catalog/job-followup.md", "job-followup", "/nowhere/SKILL.md")
    notebook.stub_project("projects/historical-notes.md", "historical-notes", [])
    notebook.stub_org("orgs/unsw-edu-au.md", "unsw.edu.au", ["unsw.edu.au"], [])
    monkeypatch.setattr(daily, "subscriptions", lambda root: {})
    monkeypatch.setattr(daily, "_clients", lambda sources: {})
    monkeypatch.setattr(daily.quota, "read", lambda config, request=None: {"unknown": "no meter"})
    pages = ["skills/catalog/job-followup.md", "projects/historical-notes.md", "orgs/unsw-edu-au.md"]
    monkeypatch.setattr(daily, "unfinished_by_recency", lambda root: [
        {"path": path, "last_activity": "", "position": n} for n, path in enumerate(pages)])
    return root


def _investigators(monkeypatch, *, found=()):
    """Each kind's investigator, faked; the pages in `found` have nothing to write from."""
    calls = []

    def answer(kind, record, **extra):
        calls.append((kind, record, extra))
        if record in found:
            raise NothingFound(f"Not written: nothing found for {record}")
        return {"changed": [record], "usage": {"input_tokens": 1}}
    monkeypatch.setattr("connectonion.rem.skill_runs.investigate_skill_page",
                        lambda root, record, dirs: answer("skill", record))
    monkeypatch.setattr(daily, "investigate", lambda root, record, title, handles, **kw: answer(
        "investigate", record, **({"retry_refused": True} if kw.get("retry_refused") else {})))
    monkeypatch.setattr(daily, "_project", lambda root, record, config: answer("project", record))
    return calls


def test_a_skill_page_goes_to_the_skill_investigator_not_the_mail_search(root, monkeypatch):
    calls = _investigators(monkeypatch)
    result = daily.run_daily(root, maintain=no_change)
    assert calls[0][:2] == ("skill", "skills/catalog/job-followup.md")
    assert result["run"]["pages"][0]["outcome"] == "accepted"
    assert result["run"]["speed"] == "fast"
    assert result["run"]["harness"] == read_config(root)["runner"]


def test_pages_with_nothing_to_write_from_take_no_slot_and_rest_a_week(root, monkeypatch):
    """On 2026-10-13 job-followup, x-reply and historical-notes took the day's three
    slots, nothing was accepted, and orgs/connectonion-com was never reached."""
    calls = _investigators(monkeypatch, found={"skills/catalog/job-followup.md", "projects/historical-notes.md"})
    result = daily.run_daily(root, maintain=no_change)
    assert [record for _, record, _ in calls] == ["skills/catalog/job-followup.md", "projects/historical-notes.md",
                                                  "orgs/unsw-edu-au.md"]
    assert result["run"]["record"] == "orgs/unsw-edu-au.md"
    # Tomorrow's first run does not ask them again.
    assert daily._found_nothing_lately(root) == {"skills/catalog/job-followup.md", "projects/historical-notes.md"}


def test_a_round_that_found_nothing_says_so_not_that_nothing_fit_the_budget(root, monkeypatch):
    _investigators(monkeypatch, found={"skills/catalog/job-followup.md", "projects/historical-notes.md",
                                       "orgs/unsw-edu-au.md"})
    result = daily.run_daily(root, maintain=no_change)
    assert result["run"]["reason"] == "nothing_found"


def test_a_project_with_messages_pending_goes_to_the_project_writer(root, monkeypatch):
    calls = _investigators(monkeypatch)
    monkeypatch.setattr("connectonion.rem.project_pages.pending",
                        lambda root, record: ([{"source": "codex:s:1"}], "first"))
    daily.run_daily(root, maintain=no_change)
    assert ("project", "projects/historical-notes.md", {}) in calls


def test_a_refused_page_is_retried_by_a_later_run_with_its_refused_material(root, monkeypatch):
    calls = _investigators(monkeypatch)
    monkeypatch.setattr(daily, "unfinished_by_recency", lambda root: [])
    assert daily.run_daily(root, maintain=no_change)["run"]["phase"] == "daily-investigation"
    remember_refusal(root, "orgs/unsw-edu-au.md", ["gmail:1"], "Candidate rejected: x", stage="investigate")
    ledger = refused_pages(root)
    ledger["orgs/unsw-edu-au.md"]["at"] = (datetime.now(timezone.utc) - timedelta(hours=21)).isoformat()
    from connectonion.rem.files import state_path, write_json
    write_json(state_path(root, "refused-investigations.json"), ledger)
    result = daily.run_daily(root, maintain=no_change)
    assert result["run"]["phase"] == "daily-update"
    assert calls == [("investigate", "orgs/unsw-edu-au.md", {"retry_refused": True})]
    assert result["run"]["pages"][0]["mode"] == "retry"
    # Tried today; not again on the next run.
    calls.clear()
    daily.run_daily(root, maintain=no_change)
    assert calls == []


def test_an_accepted_page_keeps_its_refused_rounds_in_the_daily_row(root, monkeypatch):
    """Briar's round was refused inside c50b6913 (2026-10-12), whose row said only accepted."""
    _investigators(monkeypatch)
    monkeypatch.setattr("connectonion.rem.skill_runs.investigate_skill_page", lambda root, record, dirs: {
        "changed": [record], "refused_rounds": ["Candidate rejected: Missing or duplicate citation: 22"]})
    result = daily.run_daily(root, maintain=no_change)
    assert result["run"]["pages"][0]["refused_rounds"] == ["Candidate rejected: Missing or duplicate citation: 22"]


def test_partial_maintenance_still_saves_the_owners_detected_languages(root):
    import json
    import sqlite3
    from connectonion.rem.files import read_json, write_json
    from connectonion.rem.store_build import SCHEMA, SCHEMA_VERSION

    owner = {"record": "people/avery-lin.md", "addresses": ["avery@example.test"]}
    (root / owner["record"]).write_text("# Avery Lin\n\n## Facts\n- Language: Unknown\n")
    write_json(root / ".state" / "map.json", {"owner": owner})
    body = root / ".state" / "mail/messages/gmail/avery.json"
    body.parent.mkdir(parents=True)
    body.write_text(json.dumps({"body": "我们明天再讨论一下这个项目的进展吧"}))
    with sqlite3.connect(root / ".state" / "rem.db") as db:
        db.executescript(SCHEMA)
        db.execute("insert into meta (key, value) values ('schema_version', ?)", (SCHEMA_VERSION,))
        db.execute("insert into messages values (?, 'gmail', 't', ?, '[]', '', '', ?, null)",
                   ("gmail:avery", "avery@example.test", "mail/messages/gmail/avery.json"))
    result = daily.run_daily(root, maintain=lambda root: {"outcome": "partial"})
    assert result["outcome"] == "partial" and result["investigation"] is None
    assert read_json(root / ".state" / "map.json", {})["owner"]["languages"]["languages"] == ["zh"]


@pytest.fixture
def translation_root(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    from connectonion.rem.config import set_config
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fixtures'))
    from rem_reader_notebook import build
    root = build(tmp_path / 'rem')
    monkeypatch.setattr(daily, 'subscriptions', lambda root: {})
    monkeypatch.setattr(daily, '_clients', lambda sources: {})
    monkeypatch.setattr(daily.quota, 'read', lambda config, request=None: {'unknown': 'no meter'})
    set_config(root, ['languages', 'en,zh,ja', 'limits.translations_per_day', '2'])
    monkeypatch.setattr('connectonion.rem.runner.ready', lambda config: ('', ''))
    monkeypatch.setattr('connectonion.rem.sessions.summarise_sessions', lambda *a, **kw: {})
    monkeypatch.setattr('connectonion.rem.sessions.summarise_line', lambda result: '')
    monkeypatch.setattr(daily, 'unfinished_by_recency', lambda root: [])
    return root


def test_daily_translates_changed_pages_once_with_daily_limit_and_reported_failures(translation_root, monkeypatch):
    from connectonion.rem.files import RemError
    root = translation_root
    pages = ['skills/catalog/weekly-brief.md', 'projects/harbour.md', 'orgs/fernhill-labs.md']
    monkeypatch.setattr('connectonion.rem.translate.cached', lambda root, page, language: 'current' if page == pages[0] else None)
    calls, messages = [], []

    def translator(root, page, language):
        calls.append((page, language))
        if page == pages[1]:
            raise RemError('A quoted passage changed')
        return '译文'

    maintain = lambda root: {'outcome': 'completed', 'changed': [*pages, pages[1]]}
    result = daily.run_daily(root, maintain=maintain, translate_one=translator, say=messages.append)
    report = result['maintenance']['translations']
    assert calls == [(pages[1], 'zh'), (pages[2], 'zh')]
    assert [row['outcome'] for row in report['pages']] == ['cached', 'failed', 'translated']
    assert report['attempted'] == 2
    assert report['pages'][1]['error'] == 'A quoted passage changed'
    assert any('Translation failed' in message for message in messages)
    log = next(log for log in daily.run_logs(root) if log['phase'] == 'daily-translation')
    assert log['outcome'] == 'partial' and log['pages'] == report['pages']
    daily.run_daily(root, maintain=maintain, translate_one=translator)
    assert len(calls) == 2  # Another scheduled slot shares today's allowance.


def test_daily_translates_investigation_changes_after_refresh(translation_root, monkeypatch):
    root = translation_root
    calls = []
    monkeypatch.setattr(daily, 'unfinished_by_recency', lambda root: [{'path': 'projects/harbour.md'}])
    monkeypatch.setattr('connectonion.rem.languages.refresh', lambda root: calls.append('refresh'))
    result = daily.run_daily(root, maintain=no_change,
                             investigate_one=lambda *a, **kw: {'changed': ['projects/harbour.md']},
                             translate_one=lambda root, page, language: calls.append((page, language)))
    assert calls == ['refresh', ('projects/harbour.md', 'zh')]
    assert result['maintenance']['translations']['pages'][0]['outcome'] == 'translated'


@pytest.mark.parametrize('languages, ready', [('en', True), ('zh', False)])
def test_daily_translation_skips_english_or_unready_runner(translation_root, monkeypatch, languages, ready):
    from connectonion.rem.config import set_config
    set_config(translation_root, ['languages', languages])
    monkeypatch.setattr('connectonion.rem.runner.ready', lambda config: ('', '') if ready else ('unavailable', 'sign in'))
    result = daily.run_daily(translation_root,
                             maintain=lambda root: {'outcome': 'completed', 'changed': ['projects/harbour.md']},
                             translate_one=lambda *a: pytest.fail('translator called'))
    assert 'translations' not in result['maintenance']


def test_daily_translation_respects_total_runner_cap(translation_root, monkeypatch):
    from connectonion.rem.config import set_config
    from connectonion.rem.files import write_json, state_path
    set_config(translation_root, ['limits.runner_calls_per_day', '1'])
    write_json(state_path(translation_root, 'runs/run_' + 'f' * 32 + '.json'), {
        'started_at': daily.now().isoformat(), 'runner_attempts': 1, 'outcome': 'completed'})
    result = daily.run_daily(translation_root,
                             maintain=lambda root: {'outcome': 'completed', 'changed': ['projects/harbour.md']},
                             translate_one=lambda *a: pytest.fail('daily cap exceeded'))
    assert result['maintenance']['translations']['attempted'] == 0


def _owner_page(root, investigated: str) -> str:
    """The owner's page as the first build left it, investigated on `investigated`."""
    from connectonion.rem.files import state_path, write_json
    record = "people/casey-owner.md"
    notebook = Notebook(root)
    notebook.stub_person(record, "Casey Owner", ["casey@example.com"])
    path = notebook.path(record)
    path.write_text(path.read_text().replace("not investigated yet", f"investigated {investigated} (outlook)"))
    write_json(state_path(root, "map.json"), {"owner": {"record": record, "addresses": ["casey@example.com"]}})
    return record


def test_a_later_run_refreshes_the_owners_page_once_a_day(root, monkeypatch):
    """#2720: on 2026-11-03, after 33 runs that day, the page pinned as You still
    read as of 2026-10-10, while the same rounds rewrote 39 other pages."""
    calls = _investigators(monkeypatch)
    seen = {}
    monkeypatch.setattr(daily, "investigate", lambda root, record, title, handles, **kw: (
        seen.update({record: (handles, kw.get("sent_only"), kw.get("days"))}),
        calls.append(("investigate", record, {})), {"changed": [record]})[-1])
    monkeypatch.setattr(daily, "unfinished_by_recency", lambda root: [])
    record = _owner_page(root, (datetime.now(timezone.utc) - timedelta(days=24)).date().isoformat())
    assert daily.run_daily(root, maintain=no_change)["run"]["phase"] == "daily-investigation"
    result = daily.run_daily(root, maintain=no_change)
    assert result["run"]["phase"] == "daily-update"
    row = result["run"]["pages"][0]
    assert (row["page"], row["outcome"], row["mode"]) == (record, "accepted", "owner")
    # Read the way `investigate me` reads it, over the days since it was last read.
    assert seen[record] == (["casey@example.com"], True, 25)
    calls.clear()
    daily.run_daily(root, maintain=no_change)
    assert calls == []


def test_the_owners_page_read_today_is_not_read_again(root, monkeypatch):
    calls = _investigators(monkeypatch)
    monkeypatch.setattr(daily, "unfinished_by_recency", lambda root: [])
    _owner_page(root, datetime.now(timezone.utc).date().isoformat())
    daily.run_daily(root, maintain=no_change)
    daily.run_daily(root, maintain=no_change)
    assert calls == []


def test_same_person_judgements_are_a_run_in_the_logs_and_count_against_the_days_calls(root, monkeypatch):
    """#2741: two judge calls a run were in no log, no budget and no call count."""
    from connectonion.rem import same_person
    from connectonion.rem.service import run_logs, status
    _investigators(monkeypatch)
    monkeypatch.setattr(daily, "unfinished_by_recency", lambda root: [])
    monkeypatch.setattr(same_person, "candidates", lambda root: [{"pages": ["people/a.md", "people/b.md"], "why": "x"}])
    monkeypatch.setattr(same_person, "judge", lambda root, config, limit, say: [
        {"pages": ["people/a.md", "people/b.md"], "same": False, "usage": {"input_tokens": 40}}] * limit)
    before = status(root)["runner_attempts_today"]
    result = daily.run_daily(root, maintain=no_change)
    run = next(record for record in run_logs(root) if record.get("phase") == "same-person")
    assert run["runner_attempts"] == 2 and run["usage"] == {"input_tokens": 80} and run["outcome"] == "completed"
    assert status(root)["runner_attempts_today"] == before + (result.get("run") or {}).get("runner_attempts", 0) + 2
    from connectonion.rem.quota import INVESTIGATION_PHASES
    assert "same-person" in INVESTIGATION_PHASES


def test_no_pair_to_judge_writes_no_run(root, monkeypatch):
    from connectonion.rem import same_person
    from connectonion.rem.service import run_logs
    _investigators(monkeypatch)
    monkeypatch.setattr(same_person, "candidates", lambda root: [])
    daily.run_daily(root, maintain=no_change)
    assert not [record for record in run_logs(root) if record.get("phase") == "same-person"]


def test_daily_round_waits_for_a_short_owner_command(root, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event
    from connectonion.rem.files import maintenance_lock
    from connectonion.rem.sessions import import_sessions

    entered = Event()
    sessions = import_sessions(root, consented_only=True)

    def lock(root, **options):
        entered.set()
        return maintenance_lock(root, **options)

    monkeypatch.setattr(daily, "maintenance_lock", lock)
    monkeypatch.setattr(daily, "unfinished_by_recency", lambda root: [])
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("offline", ""))
    with ThreadPoolExecutor(max_workers=1) as pool:
        with maintenance_lock(root):
            future = pool.submit(daily.run_daily, root,
                                 maintain=lambda root: {"outcome": "no_change", "sessions": sessions})
            assert entered.wait(timeout=3)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.05)
        result = future.result(timeout=3)
    assert result["outcome"] == "completed"


@pytest.mark.parametrize("stage", ["maintenance", "unfinished", "update"])
@pytest.mark.parametrize("wrapped", [False, True])
def test_scheduled_daily_cap_is_recorded_as_budget_exhausted(root, monkeypatch, stage, wrapped):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.rem import service
    from connectonion.rem.files import read_json, state_path, write_json

    config = read_config(root)
    slot = daily.now().astimezone(service.notebook_zone(config))
    write_json(state_path(root, "worker.json"), {"last_scheduled_slot": slot.isoformat()})
    write_json(state_path(root, "runs/run_cap.json"), {
        "started_at": daily.now().isoformat(), "outcome": "completed",
        "phase": "daily-investigation" if stage == "update" else "sync",
        "runner_attempts": config["limits"]["runner_calls_per_day"]})
    if stage == "update":
        _owner_page(root, "2026-01-01")

    def maintain(root, **options):
        return {"outcome": "budget_exhausted" if stage == "maintenance" else "no_change"}

    if wrapped:
        monkeypatch.setattr(service, "_scheduled_slot", lambda root: slot)
        result = service.run_scheduled(root, lambda: daily.run_daily(root, maintain=maintain))
    else:
        result = daily.run_daily(root, scheduled=True, maintain=maintain)
    worker = read_json(state_path(root, "worker.json"), {})
    assert result["outcome"] == "budget_exhausted"
    assert worker["last_scheduled_outcome"] == "budget_exhausted"
    assert worker["last_scheduled_reason"] == "the day's runner calls are spent"
    shown = CliRunner().invoke(app, ["rem", "--root", str(root), "status"])
    assert shown.exit_code == 0, shown.output
    assert "daily cap reached" in shown.output


def test_status_renders_daily_cap_as_reached():
    from rich.text import Text
    from connectonion.cli.commands.rem_status import _last_run

    rendered = Text.from_markup(_last_run({
        "outcome": "budget_exhausted", "started_at": "2026-11-05T03:00:00+00:00"}, timezone.utc)).plain
    assert "daily cap reached" in rendered
    assert "failed" not in rendered


def test_same_person_quota_starts_after_the_investigation(root, monkeypatch):
    from connectonion.rem import same_person

    meter = {"used_percent": 10, "resets_at": int((daily.now() + timedelta(days=1)).timestamp()),
             "window_minutes": 10080, "plan": "fictional"}
    monkeypatch.setattr(daily.quota, "read", lambda config: dict(meter))
    monkeypatch.setattr(daily, "unfinished_by_recency", lambda root: [{"path": "projects/historical-notes.md"}])
    monkeypatch.setattr(same_person, "candidates", lambda root: [{"pages": ["people/a.md", "people/b.md"]}])

    def investigate(*args, **options):
        meter["used_percent"] = 13
        return {"changed": ["projects/historical-notes.md"]}

    def judge(*args, **options):
        meter["used_percent"] = 14
        return [{"pages": ["people/a.md", "people/b.md"], "same": False}]

    monkeypatch.setattr(same_person, "judge", judge)
    result = daily.run_daily(root, maintain=no_change, investigate_one=investigate)
    run = next(row for row in daily.run_logs(root) if row.get("phase") == "same-person")
    assert run["quota"]["before"] == result["run"]["quota"]["after"]
    assert run["quota"]["before"]["used_percent"] == 13
    assert daily.quota.points_spent([result["run"], run], meter) == 4


def test_translation_usage_is_returned_once_and_excludes_older_runs(translation_root, monkeypatch):
    from connectonion.rem.files import state_path, write_json
    root = translation_root
    monkeypatch.setattr("connectonion.rem.translate.cached", lambda *a: None)
    write_json(state_path(root, "runs/run_old.json"), {
        "id": "run_old", "phase": "translate", "started_at": daily.now().isoformat(),
        "outcome": "completed", "usage": {"input_tokens": 9999}})

    def run(workspace, prompt, config, stage):
        (workspace / "translation.md").write_text((workspace / "page.md").read_text())
        return {"outcome": "natural", "usage": {"input_tokens": 400, "output_tokens": 10}}

    monkeypatch.setattr("connectonion.rem.runner.run_task", run)
    result = daily.run_daily(root, maintain=lambda root: {
        "outcome": "completed", "changed": ["projects/harbour.md"]})
    assert result["maintenance"]["translations"]["usage"] == {"input_tokens": 400, "output_tokens": 10}
    summary = next(log for log in daily.run_logs(root) if log["phase"] == "daily-translation")
    assert summary["usage"] is None  # The underlying translate run already owns this usage.


@pytest.mark.parametrize("failed", [False, True])
def test_translation_usage_excludes_overlapping_manual_run(translation_root, monkeypatch, failed):
    from connectonion.rem.translate import translate

    root = translation_root
    page = "projects/harbour.md"
    calls = []

    def run(workspace, prompt, config, stage):
        calls.append(workspace)
        scheduled = len(calls) == 1
        if scheduled:
            # A standalone translation of even the same page may finish during upkeep.
            translate(root, page, "zh")
        if not (scheduled and failed):
            (workspace / "translation.md").write_text((workspace / "page.md").read_text())
        return {"outcome": "natural", "usage": {
            "input_tokens": 400 if scheduled else 900, "output_tokens": 10}}

    monkeypatch.setattr("connectonion.rem.runner.run_task", run)
    result = daily.run_daily(root, maintain=lambda root: {"outcome": "completed", "changed": [page]})
    report = result["maintenance"]["translations"]
    assert len(calls) == 2
    assert report["usage"] == {"input_tokens": 400, "output_tokens": 10}
    assert report["pages"][0]["outcome"] == ("failed" if failed else "translated")



@pytest.mark.parametrize("zone, moment, day", [
    ("Pacific/Honolulu", "2026-11-06T01:00:00+00:00", "2026-11-05"),
    ("Pacific/Kiritimati", "2026-11-05T12:00:00+00:00", "2026-11-06"),
])
def test_owner_due_and_refresh_use_the_notebook_day(root, monkeypatch, zone, moment, day):
    from connectonion.rem import service
    from connectonion.rem.config import set_config
    from connectonion.rem.files import read_json, state_path

    set_config(root, ["schedule.timezone", zone])
    clock = lambda: datetime.fromisoformat(moment)
    monkeypatch.setattr(service, "now", clock)
    monkeypatch.setattr(daily, "now", clock)
    record = _owner_page(root, day)
    assert daily._owner_due(root) == []
    Notebook(root).write(record, Notebook(root).read(record).replace(f"investigated {day}", "investigated 2026-11-01"))
    [row] = daily._owner_due(root)
    monkeypatch.setattr(daily, "investigate", lambda *args, **kwargs: {})
    daily._owner(root, row, clients={}, subscriptions={})
    assert read_json(state_path(root, "owner-refresh.json"), {})["date"] == day
    assert daily._owner_due(root) == []
