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
from connectonion.rem.config import prepare, read_config
from connectonion.rem.files import Notebook
from connectonion.rem.investigate import NothingFound
from connectonion.rem.refusals import refused_pages, remember_refusal


def no_change(root):
    return {"outcome": "no_change"}


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
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
    assert report['runner_attempts'] == 2
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
    assert result['maintenance']['translations']['runner_attempts'] == 0
