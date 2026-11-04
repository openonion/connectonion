"""Native sessions write outputs; real stage preparation and validation own promotion."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import daily, native, quota, reflections, runner, service
from connectonion.rem.config import prepare, read_config
from connectonion.rem.files import Notebook, RemError, maintenance_lock, read_json, state_path, write_json


@pytest.fixture
def trial(tmp_path, monkeypatch):
    root = tmp_path / "trial"
    prepare(root)
    write_json(state_path(root, "subscriptions.json"),
               {kind: {"kind": kind, "enabled": False, "unsubscribed": True}
                for kind in ("codex", "claude-code", "gmail", "outlook")})
    write_json(state_path(root, "consent.json"), {"authorized_at": service.now().isoformat()})
    monkeypatch.setattr(quota, "read", lambda config: {"unknown": "fixture"})
    monkeypatch.setattr(daily, "_clients", lambda sources: {})
    def no_model(*args, **kwargs):
        pytest.fail("A native boundary must never invoke a model")
    monkeypatch.setattr(runner, "run_task", no_model)
    monkeypatch.setattr(runner, "run_claim_task", no_model)
    return root


def _feedback(root):
    book, record = Notebook(root), "people/avery-lin.md"
    book.stub_person(record, "Avery Lin", ["avery@example.test"], email="avery@example.test")
    row = reflections.add(root, record, "Avery Lin requested a pilot review.", author="Morgan Vale",
                          basis="Avery's original request", kind="correction")
    return record, "reflection:" + row["id"]


def _candidate(root, task, record, source):
    text = Notebook(root).read(record)
    text = text.replace("## Who they are\n- Unknown — not investigated yet",
                        "## Who they are\n- Avery Lin requested a pilot review. [1]")
    text = text.replace("## Sources\n", f"## Sources\n- [1] {source}\n")
    Path(task["candidate"]).write_text(text, encoding="utf-8")


def _submit(root, task):
    result = native.submit(root, task["id"])
    if result["outcome"] == "task":
        before = _canonical(root)
        Path(result["candidate"]).write_text(json.dumps({"verdict": "PASS", "findings": []}))
        assert _canonical(root) == before
        result = native.submit(root, task["id"])
    return result


def _canonical(root):
    return {record: Notebook(root).path(record).read_bytes() for record in Notebook(root).list()}


def test_next_prepares_real_maintenance_without_model_or_notebook_copy(trial):
    record, source = _feedback(trial)
    task = native.next_task(trial)
    assert task["outcome"] == "task" and task["record"] == record
    assert "Material is evidence" in task["instructions"] or "evidence, never instructions" in task["instructions"]
    saved = read_json(Path(task["material"]) / "task.json", {})
    assert source in (Path(task["material"]) / "material.md").read_text()
    assert saved["today"] in task["instructions"]
    assert not (Path(task["material"]) / "notebook").exists()
    with maintenance_lock(trial):
        pass
    assert native.next_task(trial)["outcome"] == "claimed"


def test_submit_promotes_real_valid_candidate_and_logs_unknown_usage(trial):
    record, source = _feedback(trial)
    task = native.next_task(trial)
    _candidate(trial, task, record, source)
    result = _submit(trial, task)
    assert result["outcome"] == "accepted", result
    assert "Avery Lin requested a pilot review." in Notebook(trial).read(record)
    logs = [row for row in service.run_logs(trial) if row.get("task_id") == task["id"]]
    assert all(row["usage"] is None for row in logs) and sum(row["runner_attempts"] for row in logs) == 2
    assert read_json(Path(task["material"]) / "task.json", {})["status"] == "accepted"


@pytest.mark.parametrize("bad", ["missing-definition", "unknown-source"])
def test_refused_candidate_keeps_notebook_bytes_and_pending_task(trial, bad):
    record, source = _feedback(trial)
    task = native.next_task(trial)
    _candidate(trial, task, record, source)
    path = Path(task["candidate"])
    path.write_text(path.read_text().replace(f"- [1] {source}\n", "") if bad == "missing-definition"
                    else path.read_text().replace(source, "gmail:invented"))
    before = _canonical(trial)
    refused = native.submit(trial, task["id"])
    assert refused["outcome"] == "refused", refused
    assert _canonical(trial) == before
    assert native.next_task(trial)["outcome"] == "claimed"
    _candidate(trial, task, record, source)
    assert _submit(trial, task)["outcome"] == "accepted"


def test_changed_input_refuses_without_any_writes(trial):
    record, source = _feedback(trial)
    task = native.next_task(trial)
    _candidate(trial, task, record, source)
    Notebook(trial).write(record, Notebook(trial).read(record) + "\nNewer user edit.\n")
    before = {path: path.read_bytes() for path in trial.rglob("*") if path.is_file()}
    with pytest.raises(RemError, match="input changed"):
        native.submit(trial, task["id"])
    assert {path: path.read_bytes() for path in trial.rglob("*") if path.is_file()} == before


def test_manual_sync_refuses_before_import_tidy_or_scrub(trial):
    _feedback(trial)
    task = native.next_task(trial)
    before = {path: path.read_bytes() for path in trial.rglob("*") if path.is_file()}
    with pytest.raises(RemError, match="a native task is pending"):
        service.run_sync(trial)
    runner.scrub_task(Path(task["material"]))
    assert {path: path.read_bytes() for path in trial.rglob("*") if path.is_file()} == before


def test_quota_floor_stops_before_collecting(trial, monkeypatch):
    _feedback(trial)
    monkeypatch.setattr(quota, "read", lambda config: {"used_percent": 95})
    result = CliRunner().invoke(app, ["rem", "--root", str(trial), "next"])
    assert result.exit_code == 0, result.output
    assert "floor" in result.output and "95%" in result.output
    assert not state_path(trial, "round.json").exists()


def test_overnight_submit_uses_prepared_date(trial, monkeypatch):
    record, source = _feedback(trial)
    task = native.next_task(trial)
    _candidate(trial, task, record, source)
    prepared = service.now()
    monkeypatch.setattr(service, "now", lambda: prepared + timedelta(hours=12))
    assert _submit(trial, task)["outcome"] == "accepted"


def test_stale_task_is_explicitly_discarded_and_logged(trial, monkeypatch):
    _feedback(trial)
    task = native.next_task(trial)
    prepared = service.now()
    monkeypatch.setattr(service, "now", lambda: prepared + timedelta(days=2))
    result = native.next_task(trial)
    assert "stale" in " ".join(result["notices"])
    assert read_json(Path(task["material"]) / "task.json", {})["status"] == "discarded"
    assert any(row.get("outcome") == "discarded" for row in service.run_logs(trial))


def test_audit_handoff_respects_daily_cap_and_resumes_tomorrow(trial, monkeypatch):
    from connectonion.rem.config import set_config
    from datetime import datetime, timezone
    set_config(trial, ["limits.runner_calls_per_day", "1", "schedule.timezone", "UTC"])
    beginning = datetime(2026, 11, 4, 20, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "now", lambda: beginning)
    record, source = _feedback(trial)
    task = native.next_task(trial)
    _candidate(trial, task, record, source)
    before = _canonical(trial)
    stopped = native.submit(trial, task["id"])
    assert stopped["outcome"] == "done" and "cap" in stopped["reason"]
    assert _canonical(trial) == before
    assert native.next_task(trial)["outcome"] == "done"
    moment = service.now()
    monkeypatch.setattr(service, "now", lambda: moment + timedelta(hours=18))
    audit = native.next_task(trial)
    assert audit["outcome"] == "task"
    assert service.daily_cap(trial)["remaining"] == 0
    Path(audit["candidate"]).write_text('{"verdict":"PASS","findings":[]}')
    assert native.submit(trial, task["id"])["outcome"] == "accepted"


def test_bad_side_output_is_refused_before_canonical_promotion(trial):
    record, source = _feedback(trial)
    task = native.next_task(trial)
    _candidate(trial, task, record, source)
    write_json(Path(task["material"]) / "review-candidates.json",
               [{"kind": "question", "subjects": ["../outside"], "question": "Fixture question", "basis": "Fixture basis"}])
    before = _canonical(trial)
    assert native.submit(trial, task["id"])["outcome"] == "refused"
    assert _canonical(trial) == before
    (Path(task["material"]) / "review-candidates.json").unlink()
    assert _submit(trial, task)["outcome"] == "accepted"


def test_discard_does_not_consume_feedback(trial):
    record, source = _feedback(trial)
    task = native.next_task(trial)
    native.next_task(trial, discard=True)
    progress = read_json(state_path(trial, "progress.json"), {})
    assert source not in progress.get("rem_local_material", [])
    from connectonion.rem import feedback
    assert any(item["source"] == source for item in feedback.plan(trial, progress)[0])


def test_new_page_maintenance_has_an_output_directory_and_promotes(trial):
    write_json(state_path(trial, "capture-queue/fixture.json"),
               {"role": "user", "source": "codex:fixture:1", "timestamp": service.now().isoformat(),
                "text": "Store release notes in Markdown.", "project": ""})
    task = native.next_task(trial)
    assert Path(task["candidate"]).is_dir()
    Notebook(Path(task["candidate"])).write("notes/release-format.md", "# Release notes\n\nStore release notes in Markdown.\n")
    result = native.submit(trial, task["id"])
    assert result["outcome"] == "accepted", result
    assert Notebook(trial).exists("notes/release-format.md")


def test_changed_original_candidate_cannot_become_a_symlink_during_audit(trial):
    record, source = _feedback(trial)
    task = native.next_task(trial)
    _candidate(trial, task, record, source)
    audit = native.submit(trial, task["id"])
    assert audit["outcome"] == "task"
    original = Path(task["candidate"])
    original.unlink()
    original.symlink_to(Notebook(trial).path(record))
    Path(audit["candidate"]).write_text('{"verdict":"PASS","findings":[]}')
    before = _canonical(trial)
    assert native.submit(trial, task["id"])["outcome"] == "refused"
    assert _canonical(trial) == before


def test_three_investigation_parts_resume_across_fresh_processes(trial):
    import subprocess
    import sys
    from connectonion.rem.mail_archive import retain_message
    book, record = Notebook(trial), "people/avery-lin.md"
    book.stub_person(record, "Avery Lin", ["avery@example.test"], email="avery@example.test")
    moment = service.now()
    write_json(state_path(trial, "map.json"), {"people": [{"record": record, "name": "Avery Lin", "addresses": ["avery@example.test"],
                                                          "mails": 3, "sent": 1, "received": 2, "last": moment.isoformat()}]})
    subs = read_json(state_path(trial, "subscriptions.json"), {})
    subs["gmail"]["unsubscribed"] = False
    write_json(state_path(trial, "subscriptions.json"), subs)
    write_json(state_path(trial, "mail/archive.json"), {"phase": "complete", "providers": ["gmail"],
               "range_start": (moment - timedelta(days=30)).isoformat(), "range_end": moment.isoformat(),
               "owner_addresses": ["morgan@example.test"]})
    for number in range(3):
        retain_message(trial, "gmail", {"id": f"mail-{number}", "date": (moment - timedelta(days=3-number)).isoformat(),
                       "from": "Avery Lin <avery@example.test>", "to": ["morgan@example.test"], "subject": f"Pilot {number}"},
                       f"Avery requested pilot {number}. " + "This fixture describes a pilot review. " * 1500,
                       fetched_at=moment.isoformat())
    # The real gather and round splitter prepare the persisted plan; no model runs.
    from connectonion.rem import investigate
    from connectonion.rem.config import set_config
    set_config(trial, ["limits.input_chars_per_batch", "50000"])
    setup = '''
import json, sys
from pathlib import Path
from connectonion.rem import daily, quota, native, runner
root = Path(sys.argv[1])
daily._clients = lambda sources: {}
quota.read = lambda config: {"unknown": "fixture"}
def forbidden(*args, **kwargs):
    raise AssertionError("native operation started a model")
runner.run_task = runner.run_claim_task = forbidden
'''
    def process(expression):
        result = subprocess.run([sys.executable, "-c", setup + f"\nprint(json.dumps({expression}))", str(trial)],
                                text=True, capture_output=True, check=True)
        return json.loads(result.stdout)
    prepared = process("native.next_task(root)")
    numbers = []
    for _ in range(12):
        if prepared["outcome"] != "task":
            break
        if prepared["stage"] == "investigate" and "audit-output.json" not in prepared["candidate"]:
            if numbers:
                assert f"Round {numbers[-1]}: NO CHANGE" in prepared["instructions"]
            numbers.append(prepared["round"])
            Path(prepared["material"], "report.md").write_text("NO CHANGE; the fixture has no new supported page claims.")
        result = process(f"native.submit(root, {prepared['id']!r})")
        if result["outcome"] == "task":
            Path(result["candidate"]).write_text('{"verdict":"PASS","findings":[]}')
            process(f"native.submit(root, {prepared['id']!r})")
        prepared = process("native.next_task(root)")
    assert numbers[:3] == [1, 2, 3], (numbers, prepared)
    cursor = read_json(state_path(trial, "round.json"), {})
    assert cursor["done"]


def test_promotion_recovers_after_process_dies_before_task_acceptance(trial, monkeypatch):
    record, source = _feedback(trial)
    task = native.next_task(trial)
    _candidate(trial, task, record, source)
    audit = native.submit(trial, task["id"])
    Path(audit["candidate"]).write_text('{"verdict":"PASS","findings":[]}')
    accept = native._accept
    def killed(*args):
        raise KeyboardInterrupt("fixture process death after atomic page write")
    monkeypatch.setattr(native, "_accept", killed)
    with pytest.raises(KeyboardInterrupt):
        native.submit(trial, task["id"])
    saved = Notebook(trial).read(record)
    monkeypatch.setattr(native, "_accept", accept)
    native.next_task(trial)
    assert Notebook(trial).read(record) == saved
    assert read_json(Path(task["material"]) / "task.json", {})["status"] == "accepted"
    assert read_json(state_path(trial, "round.json"), {}).get("pending") != task["id"]


def test_pending_looks_up_only_the_cursor_task(trial, monkeypatch):
    _feedback(trial)
    task = native.next_task(trial)
    unrelated = state_path(trial, "tasks/native-00000000000000000000000000000000/task.json")
    unrelated.parent.mkdir()
    unrelated.write_text("This historical task deliberately is not parseable JSON.")
    assert native.pending(trial)[0]["id"] == task["id"]
    with pytest.raises(RemError, match="native task is pending"):
        service.run_sync(trial)


def test_newer_source_checkpoint_is_preserved_between_feedback_tasks(trial):
    first, _ = _feedback(trial)
    other = "people/morgan-vale.md"
    Notebook(trial).stub_person(other, "Morgan Vale", [], email="morgan@example.test")
    reflections.add(trial, other, "Morgan Vale requested review.", author="Avery Lin",
                    basis="The original request", kind="correction")
    task = native.next_task(trial)
    Path(task["material"], "report.md").write_text("NO CHANGE")
    assert native.submit(trial, task["id"])["outcome"] == "accepted"
    progress = read_json(state_path(trial, "progress.json"), {})
    progress["manual-source-checkpoint"] = {"cursor": "newer"}
    write_json(state_path(trial, "progress.json"), progress)
    with pytest.raises(RemError, match="Source progress changed"):
        native.next_task(trial)
    assert read_json(state_path(trial, "progress.json"), {}) == progress
    native.next_task(trial, discard=True)
    assert read_json(state_path(trial, "progress.json"), {})["manual-source-checkpoint"] == {"cursor": "newer"}


def test_modified_archived_original_refuses_even_when_task_material_is_intact(trial):
    from connectonion.rem.mail_archive import retain_message, observed_message_path
    import hashlib
    record, _ = _feedback(trial)
    # A real archived input is handed directly to the shared runner preparation.
    row = {"id": "original-fixture", "date": service.now().isoformat(), "from": "Avery Lin <avery@example.test>",
           "to": ["morgan@example.test"], "subject": "Pilot"}
    retain_message(trial, "gmail", row, "Avery requested review.", fetched_at=row["date"])
    path = observed_message_path(trial, "gmail", row["id"])
    write_json(state_path(trial, "capture-queue/mail-fixture.json"),
               {"role": "other", "source": "gmail:" + hashlib.sha256(row["id"].encode()).hexdigest()[:12],
                "_mail_id": row["id"], "timestamp": row["date"], "text": "Avery requested review."})
    # Remove the separate feedback packet so this round selects the archive input.
    for reflection in state_path(trial, "reflections").glob("*.json"):
        reflection.unlink()
    task = native.next_task(trial)
    saved = read_json(path, {})
    saved["body"] = "The original was corrected."
    write_json(path, saved)
    with pytest.raises(RemError, match="input changed"):
        native.submit(trial, task["id"])


def test_cli_json_and_logs_expose_the_native_work(trial):
    record, source = _feedback(trial)
    cli = CliRunner()
    result = cli.invoke(app, ["rem", "--root", str(trial), "next", "--json"])
    assert result.exit_code == 0, result.output
    task = json.loads(result.stdout)["data"]
    assert task["outcome"] == "task" and task["submit"].endswith("submit " + task["id"])
    _candidate(trial, task, record, source)
    assert _submit(trial, task)["outcome"] == "accepted"
    logs = cli.invoke(app, ["rem", "--root", str(trial), "--json", "logs"])
    assert logs.exit_code == 0, logs.output
    assert task["id"] in logs.stdout


def test_translation_limit_uses_prior_rounds_from_today(trial):
    from connectonion.rem import native_round
    from connectonion.rem.config import set_config
    set_config(trial, ["languages", "zh", "limits.translations_per_day", "1"])
    book = Notebook(trial)
    book.write("notes/pilot.md", "# Pilot\n\nRead the pilot notes.\n")
    with maintenance_lock(trial):
        cursor = native_round.prepare(trial, read_config(trial), scheduled=False)
        cursor.update(changed=["notes/pilot.md"], jobs=[], summaries=[], same_left=0)
        write_json(state_path(trial, "round.json"), cursor)
        run, path = daily._reserve(trial, "daily-translation", 1, {})
        run.update(outcome="completed")
        write_json(path, run)
    result = native.next_task(trial)
    assert result["outcome"] == "done", result
    assert not any(task.get("stage") == "translate" for task in native.pending(trial))


def test_later_round_retries_held_refused_material(trial):
    from connectonion.rem.refusals import REFUSED, remember_refusal, refused_pages
    record = "people/avery-lin.md"
    Notebook(trial).stub_person(record, "Avery Lin", [], email="avery@example.test")
    item = {"role": "user", "source": "codex:held:1", "timestamp": service.now().isoformat(),
            "text": "Avery Lin requested pilot review."}
    remember_refusal(trial, record, [item["source"]], "Fixture refusal", stage="maintain", material=[item])
    ledger = refused_pages(trial)
    ledger[record]["at"] = (service.now() - timedelta(days=2)).isoformat()
    write_json(state_path(trial, REFUSED), ledger)
    # The day's first portion is complete; the later round must use the retry ledger.
    with maintenance_lock(trial):
        run, path = daily._reserve(trial, "daily-investigation", 0, {})
        run.update(outcome="completed")
        write_json(path, run)
    task = native.next_task(trial)
    assert task["stage"] == "maintain" and task["record"] == record
    assert item["text"] in task["instructions"]
    Path(task["material"], "report.md").write_text("NO CHANGE")
    assert native.submit(trial, task["id"])["outcome"] == "accepted"
    assert record not in refused_pages(trial)


def test_feedback_checkpoint_recovers_after_progress_write(trial, monkeypatch):
    from connectonion.rem import feedback
    record, source = _feedback(trial)
    task = native.next_task(trial)
    Path(task['material'], 'report.md').write_text('NO CHANGE')
    finish = feedback.finish
    def interrupted(*args, **kwargs):
        finish(*args, **kwargs)
        raise KeyboardInterrupt('after feedback checkpoint')
    monkeypatch.setattr(feedback, 'finish', interrupted)
    with pytest.raises(KeyboardInterrupt):
        native.submit(trial, task['id'])
    progress = read_json(state_path(trial, 'progress.json'), {})
    monkeypatch.setattr(feedback, 'finish', finish)
    native.next_task(trial)
    assert read_json(state_path(trial, 'progress.json'), {}) == progress
    assert read_json(state_path(trial, 'round.json'), {}).get('pending') != task['id']
    assert source in progress['rem_local_material']


def test_feedback_recovery_preserves_already_accepted_receipt(trial):
    from connectonion.rem import feedback
    _feedback(trial)
    task = native.next_task(trial)
    Path(task['material'], 'report.md').write_text('NO CHANGE')
    assert native.submit(trial, task['id'])['outcome'] == 'accepted'
    progress = read_json(state_path(trial, 'progress.json'), {})
    assert list(state_path(trial, 'feedback-promotions').glob('*.json'))
    assert feedback.plan(trial, dict(progress))[0] == []
    assert read_json(state_path(trial, 'progress.json'), {}) == progress
    assert not list(state_path(trial, 'feedback-promotions').glob('*.json'))


def test_discard_precedes_accepted_task_recovery(trial, monkeypatch):
    record, _ = _feedback(trial)
    task = native.next_task(trial)
    Path(task['material'], 'report.md').write_text('NO CHANGE')
    from connectonion.rem import native_round
    advance = native_round.advance
    def interrupted(*args):
        raise KeyboardInterrupt('before advancement')
    monkeypatch.setattr(native_round, 'advance', interrupted)
    with pytest.raises(KeyboardInterrupt):
        native.submit(trial, task['id'])
    monkeypatch.setattr(native_round, 'advance', advance)
    progress = read_json(state_path(trial, 'progress.json'), {})
    progress['newer-source'] = {'cursor': 'newer'}
    write_json(state_path(trial, 'progress.json'), progress)
    native.next_task(trial, discard=True)
    assert read_json(state_path(trial, 'progress.json'), {}).get('newer-source') == {'cursor': 'newer'}
    assert read_json(Path(task['material']) / 'task.json', {})['status'] == 'discarded'


def test_unrouted_empty_output_requires_no_change_receipt(trial):
    Notebook(trial).write('notes/existing.md', '# Existing\n\nA previous note.\n')
    write_json(state_path(trial, 'capture-queue/unrouted.json'),
               {'role': 'user', 'source': 'codex:unrouted:1', 'timestamp': service.now().isoformat(),
                'text': 'Store release notes in Markdown.', 'project': ''})
    task = native.next_task(trial)
    assert Path(task['candidate']).is_dir()
    before = _canonical(trial)
    progress = read_json(state_path(trial, 'progress.json'), {})
    result = native.submit(trial, task['id'])
    assert result['outcome'] == 'refused', result
    assert 'no-change' in result['reason']
    assert _canonical(trial) == before
    assert read_json(state_path(trial, 'progress.json'), {}) == progress
    saved = read_json(Path(task['material']) / 'task.json', {})
    sources = sorted({item['source'] for item in saved['task']['items'] if item.get('source')})
    write_json(Path(task['material']) / 'completion.json',
               {'status': 'no_change', 'sources': sources, 'reason': 'Reviewed; no new supported claims.'})
    assert native.submit(trial, task['id'])['outcome'] == 'accepted'


def test_refused_submit_points_to_resubmitting_the_pending_task(trial):
    write_json(state_path(trial, 'capture-queue/unrouted.json'),
               {'role': 'user', 'source': 'codex:unrouted:1', 'timestamp': service.now().isoformat(),
                'text': 'Store release notes in Markdown.', 'project': ''})
    task = native.next_task(trial)
    cli = CliRunner()
    args = ['rem', '--root', str(trial), 'submit', task['id']]
    refused = cli.invoke(app, args)
    assert refused.exit_code == 1, refused.output
    assert f'Next: co rem --root {trial} submit {task["id"]}' in refused.output
    saved = read_json(Path(task['material']) / 'task.json', {})
    sources = sorted({item['source'] for item in saved['task']['items'] if item.get('source')})
    write_json(Path(task['material']) / 'completion.json',
               {'status': 'no_change', 'sources': sources, 'reason': 'Reviewed; no new supported claims.'})
    accepted = cli.invoke(app, args)
    assert accepted.exit_code == 0 and 'accepted' in accepted.output, accepted.output
    assert f'Next: co rem --root {trial} next' in accepted.output


def _summary_task(root):
    from connectonion.rem import sessions, native_round
    transcript = root.parent / 'rollout-fictional.jsonl'
    rows = [{'type': 'session_meta', 'payload': {'id': 'fictional-session', 'cwd': '/work/cedar',
                                               'source': 'cli', 'originator': 'codex_cli_rs'}},
            {'type': 'response_item', 'timestamp': service.now().isoformat(), 'payload': {
                'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'Build the pilot reader.'}]}}]
    transcript.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    from zoneinfo import ZoneInfo
    progress = {'files': {}, 'sessions': {}, 'settings': {'timezone': 'UTC'}}
    counts = {'imported': 0, 'updated': 0, 'unchanged': 0}
    sessions._import_file(transcript, 'codex', service.now() - timedelta(days=1), Notebook(root), {},
                          ZoneInfo('UTC'), progress, counts)
    assert counts['imported'] == 1
    write_json(state_path(root, 'sessions.json'), progress)
    with maintenance_lock(root):
        cursor = native_round.prepare(root, read_config(root), scheduled=False)
        write_json(state_path(root, 'sessions.json'), progress)
        cursor.update(jobs=[], same_left=0)
        write_json(state_path(root, 'round.json'), cursor)
    task = native.next_task(root)
    assert task['stage'] == 'sessions-summary'
    Path(task['candidate']).write_text(json.dumps({'sessions': [{'id': 's1', 'title': 'Pilot reader',
        'summary': 'Avery requested a pilot reader.', 'tags': ['pilot'], 'decisions': [], 'followups': []}]}))
    return task, transcript


@pytest.mark.parametrize('boundary', ['summary', 'page', 'tags', 'accept'])
def test_summary_promotion_recovers_every_write_boundary(trial, monkeypatch, boundary):
    from connectonion.rem import sessions
    task, _ = _summary_task(trial)
    write = sessions.write_json
    page_write = Notebook.write
    accept = native._accept
    def interrupted_json(path, value):
        write(path, value)
        if (boundary == 'summary' and path == sessions.summary_path(trial, 'codex:fictional-session')
                or boundary == 'tags' and path == state_path(trial, 'session-tags.json')):
            raise KeyboardInterrupt('after canonical JSON write')
    def interrupted_page(book, record, text):
        result = page_write(book, record, text)
        if boundary == 'page' and record == task['record']:
            raise KeyboardInterrupt('after canonical page write')
        return result
    def interrupted_accept(*args):
        raise KeyboardInterrupt('before task acceptance')
    monkeypatch.setattr(sessions, 'write_json', interrupted_json)
    monkeypatch.setattr(Notebook, 'write', interrupted_page)
    if boundary == 'accept':
        monkeypatch.setattr(native, '_accept', interrupted_accept)
    with pytest.raises(KeyboardInterrupt):
        native.submit(trial, task['id'])
    monkeypatch.setattr(sessions, 'write_json', write)
    monkeypatch.setattr(Notebook, 'write', page_write)
    monkeypatch.setattr(native, '_accept', accept)
    native.next_task(trial)
    assert read_json(Path(task['material']) / 'task.json', {})['status'] == 'accepted'
    assert '# Pilot reader' in Notebook(trial).read(task['record'])
    assert read_json(state_path(trial, 'session-tags.json'), {}) == {'pilot': 1}


def _same_person_task(root):
    from connectonion.rem import native_round
    book = Notebook(root)
    for record, name, address in [('people/avery.md', 'Avery', 'avery@home.example'),
                                  ('people/avery-lin.md', 'Avery Lin', 'avery@work.example')]:
        book.stub_person(record, name, [address], email=address)
    book.write('notes/pilot.md', '# Pilot\n\nContact [Avery](../people/avery.md) or [Avery Lin](../people/avery-lin.md).\n')
    with maintenance_lock(root):
        cursor = native_round.prepare(root, read_config(root), scheduled=False)
        cursor.update(jobs=[], summaries=[])
        write_json(state_path(root, 'round.json'), cursor)
    task = native.next_task(root)
    assert task['stage'] == 'same-person'
    Path(task['candidate']).write_text(json.dumps({'same': True, 'address_role': 'their own',
                                                  'reason': 'The fictional pilot identifies both addresses.'}))
    return task


@pytest.mark.parametrize('boundary', ['page', 'archive', 'aliases', 'relink', 'verdict', 'accept'])
def test_same_person_promotion_recovers_every_write_boundary(trial, monkeypatch, boundary):
    from connectonion.rem import merge, same_person
    task = _same_person_task(trial)
    page_write, replace = Notebook.write, Path.replace
    merge_write, verdict_write, accept = merge.write_json, same_person.write_json, native._accept
    def interrupted_page(book, record, text):
        result = page_write(book, record, text)
        if boundary == 'page' and record.startswith('people/') or boundary == 'relink' and record == 'notes/pilot.md':
            raise KeyboardInterrupt('after page write')
        return result
    def interrupted_archive(path, target):
        result = replace(path, target)
        if boundary == 'archive' and 'archived' in str(target):
            raise KeyboardInterrupt('after archive')
        return result
    def interrupted_merge(path, value):
        merge_write(path, value)
        if boundary == 'aliases' and path == state_path(trial, merge.ALIASES):
            raise KeyboardInterrupt('after aliases')
    def interrupted_verdict(path, value):
        verdict_write(path, value)
        if boundary == 'verdict' and path == state_path(trial, same_person.VERDICTS):
            raise KeyboardInterrupt('after verdict')
    def interrupted_accept(*args):
        raise KeyboardInterrupt('before acceptance')
    monkeypatch.setattr(Notebook, 'write', interrupted_page)
    monkeypatch.setattr(Path, 'replace', interrupted_archive)
    monkeypatch.setattr(merge, 'write_json', interrupted_merge)
    monkeypatch.setattr(same_person, 'write_json', interrupted_verdict)
    if boundary == 'accept':
        monkeypatch.setattr(native, '_accept', interrupted_accept)
    with pytest.raises(KeyboardInterrupt):
        native.submit(trial, task['id'])
    monkeypatch.setattr(Notebook, 'write', page_write)
    monkeypatch.setattr(Path, 'replace', replace)
    monkeypatch.setattr(merge, 'write_json', merge_write)
    monkeypatch.setattr(same_person, 'write_json', verdict_write)
    monkeypatch.setattr(native, '_accept', accept)
    native.next_task(trial)
    assert read_json(Path(task['material']) / 'task.json', {})['status'] == 'accepted'
    assert len(Notebook(trial).list('people')) == 1
    aliases = merge.aliases(trial)
    old, = aliases
    kept = aliases[old]['into']
    assert (trial / '.state/archived' / old).is_file()
    assert f'../{kept}' in Notebook(trial).read('notes/pilot.md')
    assert next(iter(read_json(state_path(trial, same_person.VERDICTS), {}).values()))['same']


def test_native_completion_records_quota_points_without_usage(trial, monkeypatch):
    window = {'resets_at': int(service.now().timestamp()) + 86400, 'window_minutes': 7 * 24 * 60}
    monkeypatch.setattr(quota, 'read', lambda config: {'used_percent': 20, **window})
    task = _same_person_task(trial)
    monkeypatch.setattr(quota, 'read', lambda config: {'used_percent': 40, **window})
    assert native.submit(trial, task['id'])['outcome'] == 'accepted'
    rows = [row for row in service.run_logs(trial) if row.get('task_id') == task['id']]
    assert rows[0]['usage'] is None
    assert rows[0]['quota']['after'] == {'used_percent': 40, **window}
    assert quota.points_spent(rows, {'used_percent': 40, **window}) == 20


def test_summary_binds_original_transcript_revision(trial):
    task, transcript = _summary_task(trial)
    transcript.write_text(transcript.read_text() + json.dumps({'type': 'response_item',
        'timestamp': service.now().isoformat(), 'payload': {'type': 'message', 'role': 'user',
        'content': [{'type': 'input_text', 'text': 'Also change the pilot scope.'}]}}) + '\n')
    before = _canonical(trial)
    with pytest.raises(RemError, match='input changed'):
        native.submit(trial, task['id'])
    assert _canonical(trial) == before


def _translation_task(root):
    from connectonion.rem import native_round
    from connectonion.rem.config import set_config
    set_config(root, ['languages', 'zh'])
    Notebook(root).write('notes/pilot.md', '# Pilot\n\nRead the pilot notes.\n')
    with maintenance_lock(root):
        cursor = native_round.prepare(root, read_config(root), scheduled=False)
        cursor.update(changed=['notes/pilot.md'], jobs=[], summaries=[], same_left=0)
        write_json(state_path(root, 'round.json'), cursor)
    task = native.next_task(root)
    assert task['stage'] == 'translate'
    Path(task['candidate']).write_text('# Pilot\n\n阅读试点笔记。\n')
    return task


def _extraction_task(root):
    from connectonion.rem import native_round, extract
    write_json(state_path(root, 'capture-queue/extract.json'),
               {'role': 'user', 'source': 'codex:extract:1', 'timestamp': service.now().isoformat(),
                'text': 'Review the pilot release notes.', 'project': ''})
    with maintenance_lock(root):
        cursor = native_round.prepare(root, read_config(root), scheduled=False)
        cursor['batch']['record']['extracted'] = True
        cursor['batch']['digested'] = None
        cursor.update(jobs=[], summaries=[], same_left=0)
        write_json(state_path(root, 'round.json'), cursor)
    task = native.next_task(root)
    assert task['stage'] == 'extract'
    Path(task['candidate']).write_text(extract.NOTHING)
    return task


@pytest.mark.parametrize('handler', ['extract', 'translate', 'sessions'])
def test_unrelated_lookup_edits_do_not_invalidate_non_page_tasks(trial, handler):
    book = Notebook(trial)
    book.stub_person('people/morgan.md', 'Morgan Vale', [], email='morgan@example.test')
    book.stub_org('orgs/cedar.md', 'Cedar Labs', [])
    task = {'extract': _extraction_task, 'translate': _translation_task,
            'sessions': lambda root: _summary_task(root)[0]}[handler](trial)
    saved = read_json(Path(task['material']) / 'task.json', {})
    assert str(book.path('people/morgan.md')) not in saved['inputs']
    assert str(book.path('orgs/cedar.md')) not in saved['inputs']
    book.write('people/morgan.md', book.read('people/morgan.md') + '\nMorgan reviewed the pilot.\n')
    book.write('orgs/cedar.md', book.read('orgs/cedar.md') + '\nCedar Labs reviewed the pilot.\n')
    book.stub_person('people/ellis.md', 'Ellis Reed', [], email='ellis@example.test')
    assert native.submit(trial, task['id'])['outcome'] == 'accepted'


def test_native_maintenance_remembers_no_change_and_clears_on_change(trial):
    from connectonion.rem.leads import cooling
    record, source = _feedback(trial)
    task = native.next_task(trial)
    Path(task['material'], 'report.md').write_text('NO CHANGE')
    assert native.submit(trial, task['id'])['outcome'] == 'accepted'
    assert cooling(trial, [record]) == [record]
    reflections.add(trial, record, 'Avery Lin requested a pilot review.', author='Morgan Vale',
                    basis='A new explicit request', kind='correction')
    task = native.next_task(trial, discard=True)
    assert task['record'] == record
    saved = read_json(Path(task['material']) / 'task.json', {})
    source = next(item['source'] for item in saved['task']['items'] if item.get('feedback_revision'))
    _candidate(trial, task, record, source)
    assert _submit(trial, task)['outcome'] == 'accepted'
    assert cooling(trial, [record]) == []


def test_next_claims_task_and_second_caller_sees_takeover_instructions(trial):
    import os
    _feedback(trial)
    task = native.next_task(trial)
    saved = read_json(Path(task['material']) / 'task.json', {})
    assert saved['claimed_by']['pid'] == os.getpid()
    since = saved['claimed_by']['started_at']
    before = {path: path.read_bytes() for path in trial.rglob('*') if path.is_file()}
    result = CliRunner().invoke(app, ['rem', '--root', str(trial), 'next'])
    assert result.exit_code == 0, result.output
    assert f"task {task['id']} is being worked on since {since}; co rem next --discard to take it over" in result.output
    assert 'instructions' not in native.next_task(trial)
    assert {path: path.read_bytes() for path in trial.rglob('*') if path.is_file()} == before
    replacement = native.next_task(trial, discard=True)
    assert replacement['outcome'] == 'task' and replacement['id'] != task['id']
    assert read_json(Path(replacement['material']) / 'task.json', {})['claimed_by']['pid'] == os.getpid()


@pytest.mark.parametrize('handler', ['sessions', 'same-person'])
def test_commit_recovery_preserves_newer_canonical_edits(trial, monkeypatch, handler):
    task = _summary_task(trial)[0] if handler == 'sessions' else _same_person_task(trial)
    accept = native._accept
    def interrupted(*args):
        raise KeyboardInterrupt('before acceptance')
    monkeypatch.setattr(native, '_accept', interrupted)
    with pytest.raises(KeyboardInterrupt):
        native.submit(trial, task['id'])
    monkeypatch.setattr(native, '_accept', accept)
    record = task['record'] if handler == 'sessions' else Notebook(trial).list('people')[0]
    book = Notebook(trial)
    book.write(record, book.read(record) + '\nA newer manual correction.\n')
    before = _canonical(trial)
    with pytest.raises(RemError, match='changed'):
        native.next_task(trial)
    assert _canonical(trial) == before
    native.next_task(trial, discard=True)
    assert 'A newer manual correction.' in book.read(record)


@pytest.mark.parametrize('handler', ['sessions', 'same-person'])
def test_stale_committed_task_recovers_before_automatic_discard(trial, monkeypatch, handler):
    task = _summary_task(trial)[0] if handler == 'sessions' else _same_person_task(trial)
    accept = native._accept
    def interrupted(*args):
        raise KeyboardInterrupt('before acceptance')
    monkeypatch.setattr(native, '_accept', interrupted)
    with pytest.raises(KeyboardInterrupt):
        native.submit(trial, task['id'])
    monkeypatch.setattr(native, '_accept', accept)
    moment = service.now()
    monkeypatch.setattr(service, 'now', lambda: moment + timedelta(days=2))
    native.next_task(trial)
    assert read_json(Path(task['material']) / 'task.json', {})['status'] == 'accepted'



def _managed_retry_task(root):
    from connectonion.rem import feedback, native_round
    from connectonion.rem.refusals import remember_refusal, refused_pages
    record, source = _feedback(root)
    material = feedback.plan(root, read_json(state_path(root, 'progress.json'), {}))[0]
    remember_refusal(root, record, [source], 'Fictional refusal', stage='maintain', material=material)
    with maintenance_lock(root):
        cursor = native_round.prepare(root, read_config(root), scheduled=False)
        cursor['batch']['done'] = True
        cursor.update(jobs=[{'kind': 'retry', 'record': record, 'entry': refused_pages(root)[record]}],
                      summaries=[], same_left=0)
        write_json(state_path(root, 'round.json'), cursor)
    task = native.next_task(root)
    assert read_json(Path(task['material']) / 'task.json', {})['operation'] == 'retry'
    Path(task['material'], 'report.md').write_text('NO CHANGE')
    return task


@pytest.mark.parametrize('newer', [False, True])
def test_managed_retry_checkpoint_recovers_without_rewinding_progress(trial, monkeypatch, newer):
    from connectonion.rem import feedback
    task = _managed_retry_task(trial)
    finish = feedback.finish
    def interrupted(*args, **kwargs):
        finish(*args, **kwargs)
        raise KeyboardInterrupt('after managed feedback checkpoint')
    monkeypatch.setattr(feedback, 'finish', interrupted)
    with pytest.raises(KeyboardInterrupt):
        native.submit(trial, task['id'])
    monkeypatch.setattr(feedback, 'finish', finish)
    progress = read_json(state_path(trial, 'progress.json'), {})
    if newer:
        progress['newer-source'] = {'cursor': 'newer'}
        write_json(state_path(trial, 'progress.json'), progress)
        with pytest.raises(RemError, match='Source progress changed'):
            native.next_task(trial)
        native.next_task(trial, discard=True)
    else:
        native.next_task(trial)
    assert read_json(state_path(trial, 'progress.json'), {}) == progress
