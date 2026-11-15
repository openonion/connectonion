"""Catchup runs the real exec path, with fresh limits and an unmoved clock."""

import json
import re
from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import daily, depth, native, native_round, quota, runner, schedule, service
from connectonion.rem.config import prepare, read_config, set_config
from connectonion.rem.files import Notebook, read_json, state_path, write_json

pytestmark = pytest.mark.usefixtures('rem_clock')
SOURCE = 'codex:fixture:7'


@pytest.fixture
def book(tmp_path, monkeypatch):
    prepare(tmp_path)
    set_config(tmp_path, ['schedule.timezone', 'UTC'])
    set_config(tmp_path, ['limits.abstract_rounds_per_night', '1'])
    write_json(state_path(tmp_path, 'subscriptions.json'), {})
    write_json(state_path(tmp_path, 'consent.json'), {'authorized_at': service.now().isoformat()})
    monkeypatch.setattr(quota, 'read', lambda config: {'unknown': 'fixture'})
    monkeypatch.setattr(daily, '_clients', lambda sources: {})
    monkeypatch.setattr(runner, 'ready', lambda config: ('', ''))
    for name in ('enrich', 'muse'):
        monkeypatch.setattr(depth.muse, name, lambda *a, **kw: {})
    return Notebook(tmp_path)


def backlog(book, count):
    book.write('sessions/backlog.md', '# Backlog\n\n## Decisions\n'
               + '\n'.join(f'- “Choice {i}.” [1]' for i in range(count))
               + f'\n\n## Sources\n- [1] {SOURCE}\n')


@pytest.fixture
def model(monkeypatch):
    calls, modes = [], []

    def run(directory, prompt, config, stage, **options):
        assert stage == 'abstract', stage
        packet = read_json(directory / 'material.json', [])
        calls.append(packet)
        if modes and modes.pop(0) == 'empty':
            return {'result': 'No change', 'usage': {'input_tokens': 10}}
        for item in packet:
            for words in re.findall('“([^”]+)”', item['text']):
                record = f'decisions/choice-{words.split()[1].strip(".")}.md'
                Notebook(directory / 'notebook').write(record,
                    f'# A choice\n\n“{words}” [1]\n\n## Sources\n- [1] {SOURCE}\n')
        return {'result': 'Captured choices', 'usage': {'input_tokens': 10}}

    monkeypatch.setattr(runner, 'run_task', run)
    return calls, modes


def invoke(book, *args, json_out=False):
    return CliRunner().invoke(app, ['rem', '--root', str(book.root),
                                   *(['--json'] if json_out else []), 'catchup', *args])


def test_catchup_reports_calendar_for_each_round(book, model, monkeypatch):
    from connectonion.rem import calendar
    backlog(book, 40)
    calls = []
    monkeypatch.setattr(calendar, 'available', lambda kind: kind == 'google')
    monkeypatch.setattr(calendar, 'calendar_events', lambda *args: calls.append(args) or [])
    result = invoke(book, '--nights', '2', json_out=True)
    assert result.exit_code == 0, result.output
    rows = json.loads(result.stdout)['data']['nights']
    assert len(calls) == len(rows) == 2
    assert all(row['calendar'] == {'events': 0, 'read': ['google'], 'errors': {}, 'capped': []} for row in rows)


def test_catchup_prints_calendar_result_in_each_night(book, model, monkeypatch):
    from connectonion.rem import calendar
    backlog(book, 20)
    monkeypatch.setattr(calendar, 'available', lambda kind: kind == 'google')
    monkeypatch.setattr(calendar, 'calendar_events', lambda *args: [])
    result = invoke(book)
    assert result.exit_code == 0, result.output
    assert '0 calendar events saved' in next(line for line in result.stdout.splitlines() if line.startswith('Night 1:'))


def test_two_nights_reuse_exec_reset_abstract_and_print_lines(book, model, monkeypatch):
    backlog(book, 60)
    original, rounds = schedule.exec_round, []

    def counted(root, **options):
        rounds.append(options)
        return original(root, **options)

    monkeypatch.setattr(schedule, 'exec_round', counted)
    result = invoke(book, '--nights', '2')
    assert result.exit_code == 0, result.output
    assert len(rounds) == 2 and all(row.get('scheduled') is False for row in rounds)
    assert len(model[0]) == 2 and len(book.list('decisions')) == 40
    assert 'Night 1: 0 mail read · 0 sessions read · 20 pages written · 20 decisions written · 0 pages translated' in result.output
    assert 'Night 2: 0 mail read · 0 sessions read · 20 pages written · 20 decisions written · 0 pages translated' in result.output
    assert 'Done: 2 nights · 40 pages written · 40 decisions written · 0 pages translated' in result.output
    assert result.output.rstrip().endswith(f'Next: co rem --root {book.root} open')


def test_each_night_runs_exec_then_the_default_logged_deepen_slot(book, model, monkeypatch):
    from connectonion.cli.commands import rem_commands
    backlog(book, 60)
    records = [f'people/person-{i}.md' for i in range(4)]
    for record, name in zip(records, ('Avery', 'Blake', 'Cameron', 'Drew')):
        book.write(record, f'# {name}\n')
    set_config(book.root, ['limits.depth_workers', '2'])
    exec_round, slot, order = schedule.exec_round, depth.slot, []

    def execute(root, **options):
        order.append('exec')
        return exec_round(root, **options)

    def deepen(root, **options):
        order.append('deepen')
        assert options['stage'] is rem_commands._depth_stage
        assert callable(options['say'])
        assert 'pages' not in options and 'records' not in options
        return slot(root, **options)

    monkeypatch.setattr(schedule, 'exec_round', execute)
    monkeypatch.setattr(depth, 'slot', deepen)
    result = invoke(book, '--nights', '2')
    assert result.exit_code == 0, result.output
    assert order == ['exec', 'deepen', 'exec', 'deepen']
    lines = result.stdout.splitlines()
    assert '3 pages deepened' in next(line for line in lines if line.startswith('Night 1:'))
    assert '1 page deepened' in next(line for line in lines if line.startswith('Night 2:'))
    assert '4 pages deepened' in next(line for line in lines if line.startswith('Done:'))
    assert set(read_json(state_path(book.root, 'depth.json'), {})) == set(records)
    logs = service.run_logs(book.root)
    assert sum(row['phase'] in ('enrich', 'muse') for row in logs) == 8


@pytest.mark.parametrize('outcome,reason,productive', [
    ('refused', 'candidate rejected', True), ('busy', 'task still running', True),
    ('done', 'Codex quota floor reached', True), ('done', 'round done', False),
])
def test_deepen_is_skipped_when_exec_stops_catchup(book, monkeypatch, outcome, reason, productive):
    from connectonion.rem import catchup

    def execute(root, **options):
        write_json(state_path(root, 'round.json'), {'catchup_night': catchup.number(root),
                   'changed': ['people/person.md'] if productive else []})
        return {'outcome': outcome, 'reason': reason}

    monkeypatch.setattr(schedule, 'exec_round', execute)
    monkeypatch.setattr(depth, 'slot', lambda *a, **kw: pytest.fail('deepened after exec stopped'))
    result = invoke(book, '--nights', '2')
    assert result.exit_code == int(outcome != 'done'), result.output
    assert 'Night 2:' not in result.stdout
    assert '0 pages deepened (exec stopped:' in result.stdout
    assert ('produced nothing' if not productive else reason) in result.stdout


def test_spent_deepen_budget_still_counts_each_night(book, model, monkeypatch):
    backlog(book, 60)
    book.write('people/person.md', '# Person\n')
    monkeypatch.setattr(depth, 'spent', lambda *a: 30)
    result = invoke(book, '--nights', '2')
    assert result.exit_code == 0, result.output
    for prefix in ('Night 1:', 'Night 2:', 'Done: 2 nights'):
        line = next(line for line in result.stdout.splitlines() if line.startswith(prefix))
        assert '0 pages deepened (deepening has used 30 of its 30-point weekly budget)' in line
    assert len(model[0]) == 2
    assert not state_path(book.root, 'depth.json').exists()


def test_no_qualifying_pages_still_counts_the_night_and_explains_zero(book, model):
    backlog(book, 40)
    result = invoke(book, '--nights', '2', json_out=True)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)['data']
    assert len(data['nights']) == 2 and data['deepened'] == 0
    assert all(row['deepened'] == 0 and row['deepen_reason'] == 'no qualifying pages'
               for row in data['nights'])


@pytest.mark.parametrize('completed', [0, 1])
def test_deepen_interruption_keeps_enrich_work_and_reports_it(book, model, monkeypatch, completed):
    backlog(book, 20)
    records = [f'people/person-{i}.md' for i in range(completed + 1)]
    for record, name in zip(records, ('Avery', 'Blake')):
        book.write(record, f'# {name}\n')
    set_config(book.root, ['limits.depth_workers', '1'])

    def enrich(root, page, **options):
        book.write(page, book.read(page) + '\nSaved enrich work.\n')
        return {'changed': [page]}

    def interrupt(root, page, **options):
        if page == records[-1]:
            raise KeyboardInterrupt
        return {}

    monkeypatch.setattr(depth.muse, 'enrich', enrich)
    monkeypatch.setattr(depth.muse, 'muse', interrupt)
    result = invoke(book, '--nights', '2')
    assert result.exit_code == 130, result.output
    assert all('Saved enrich work.' in book.read(record) for record in records)
    assert all(record in result.output for record in records) and 'and kept' in result.output
    assert 'Night 2:' not in result.output
    assert f"{completed} {'page' if completed == 1 else 'pages'} deepened (deepening interrupted)" in result.output
    assert set(read_json(state_path(book.root, 'depth.json'), {})) == set(records[:-1])
    assert {row['phase']: row['outcome'] for row in service.run_logs(book.root)
            if row.get('record') == records[-1] and row['phase'] in ('enrich', 'muse')
            } == {'enrich': 'completed', 'muse': 'interrupted'}


def test_totals_do_not_attach_a_later_empty_slot_reason_to_deepened_pages(book, model):
    backlog(book, 40)
    book.write('people/person.md', '# Person\n')
    result = invoke(book, '--nights', '2')
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert '0 pages deepened (no qualifying pages)' in next(line for line in lines if line.startswith('Night 2:'))
    total = next(line for line in lines if line.startswith('Done:'))
    assert total.endswith('1 page deepened')


def test_failed_deepen_stages_are_visible_in_the_night_line(book, model, monkeypatch):
    backlog(book, 20)
    book.write('people/person.md', '# Person\n')

    def fail(*args, **options):
        raise runner.RunFailed('fixture stage failed', {'input_tokens': 10})

    for name in ('enrich', 'muse'):
        monkeypatch.setattr(depth.muse, name, fail)
    result = invoke(book)
    assert result.exit_code == 0, result.output
    line = next(line for line in result.stdout.splitlines() if line.startswith('Night 1:'))
    assert '1 page deepened' in line  # Count the same round records as scheduled sync.
    assert 'enrich failed: fixture stage failed' in line
    assert 'muse failed: fixture stage failed' in line


def test_default_one_night_and_later_invocation_gets_a_fresh_night(book, model):
    backlog(book, 60)
    for _ in range(2):
        result = invoke(book)
        assert result.exit_code == 0, result.output
        assert 'Done: 1 night' in result.output
    assert len(model[0]) == 2 and len(book.list('decisions')) == 40


@pytest.mark.parametrize('empty_model', [False, True])
def test_night_that_produces_nothing_stops(book, model, empty_model):
    if empty_model:
        backlog(book, 60)
        model[1].append('empty')
    result = invoke(book, '--nights', '5')
    assert result.exit_code == int(empty_model), result.output
    assert 'Night 1:' in result.output and 'Night 2:' not in result.output
    assert 'Stopped: night 1 produced nothing' in result.output
    assert len(model[0]) == int(empty_model)


@pytest.mark.parametrize('between', [False, True])
@pytest.mark.parametrize('floor', ['usage', 'weekly'])
def test_quota_floor_stops_with_plain_reason(book, model, monkeypatch, rem_clock, floor, between):
    backlog(book, 60)
    meter = {'used_percent': 90 if floor == 'usage' else 20,
             'resets_at': (rem_clock + timedelta(days=5)).timestamp(), 'window_minutes': 10080}
    monkeypatch.setattr(quota, 'meter', lambda *a: {'unknown': 'fixture'} if between and not model[0] else meter)
    monkeypatch.setattr(quota, 'points_spent', lambda *a: 100)
    reason = quota.blocks(meter, 100, read_config(book.root)['limits'])
    result = invoke(book, '--nights', '3')
    assert result.exit_code == 0, result.output
    assert f'Stopped: {reason}' in result.output
    assert len(model[0]) == int(between)
    assert len(book.list('decisions')) == 20 * int(between)
    assert result.output.rstrip().endswith(f'Next: co rem --root {book.root} open')


def test_daily_call_cap_resets_and_real_schedule_is_unchanged(book, model, rem_clock, monkeypatch):
    backlog(book, 60)
    set_config(book.root, ['limits.runner_calls_per_day', '1'])
    worker = {'enabled': True, 'last_scheduled_slot': (rem_clock - timedelta(days=1)).isoformat()}
    write_json(state_path(book.root, 'worker.json'), worker)
    config = read_config(book.root)
    before_due = native_round.scheduled_slot(book.root, config)
    before_next = service.next_slot(config, service.notebook_zone(config), worker['last_scheduled_slot'])
    result = invoke(book, '--nights', '2')
    assert result.exit_code == 0, result.output
    assert len(model[0]) == 2
    assert service.now() == rem_clock
    assert service.notebook_today(book.root) == rem_clock.date()
    assert service.next_slot(read_config(book.root), service.notebook_zone(config), worker['last_scheduled_slot']) == before_next
    assert native_round.scheduled_slot(book.root, config) == before_due
    assert read_json(state_path(book.root, 'worker.json'), {}) == worker
    # Neither tonight's call cap nor its abstract reservation was consumed.
    assert service.daily_cap(book.root)['remaining'] == 1
    assert not state_path(book.root, 'abstract-night.json').exists()
    set_config(book.root, ['limits.runner_calls_per_day', '200'])
    tomorrow = rem_clock + timedelta(days=1)
    monkeypatch.setattr(service, 'now', lambda: tomorrow)
    assert schedule.exec_round(book.root, scheduled=True)['reason'] == 'round done'
    assert len(model[0]) == 3
    assert service.worker_state(book.root)['last_scheduled_slot'] != worker['last_scheduled_slot']


def test_capped_nights_read_sources_again_and_keep_unfinished_work(book, model, monkeypatch):
    backlog(book, 60)
    set_config(book.root, ['limits.runner_calls_per_day', '1'])
    original, reads = native_round.prepare, []

    def counted(root, config, **options):
        reads.append(options)
        return original(root, config, **options)

    monkeypatch.setattr(native_round, 'prepare', counted)
    result = invoke(book, '--nights', '2')
    assert result.exit_code == 0, result.output
    assert len(reads) == 2, 'every catchup night must reread sources'
    assert len(model[0]) == 2


def test_ordinary_abstract_limit_survives_catchup(book, model):
    backlog(book, 60)
    marker = {'day': '2026-09-07', 'rounds': 1, 'stopped': False}
    write_json(state_path(book.root, 'abstract-night.json'), marker)
    assert invoke(book).exit_code == 0
    assert read_json(state_path(book.root, 'abstract-night.json'), {}) == marker
    assert schedule.exec_round(book.root, scheduled=False)['reason'] == 'round done'
    assert len(model[0]) == 1


def test_daily_phase_and_cursor_counters_reset_each_night(book, monkeypatch):
    from connectonion.rem import catchup
    phases, scopes = [], []

    def one(root, **options):
        cursor = native_round.prepare(root, read_config(root), scheduled=False)
        native_round._reset_attempts(root, cursor)
        phases.append(cursor['phase'])
        scopes.append(cursor['task_day'])
        assert cursor['same_left'] == 3 and cursor['same_new_left'] == 10
        assert cursor['draft_attempts'] == cursor['translation_attempts'] == []
        cursor.update(same_left=0, same_new_left=0, draft_attempts=[['draft', 1]],
                      translation_attempts=[['zh', 'people/fern.md']], changed=['people/fern.md'])
        native_round.finish(root, cursor)
        return {'outcome': 'done', 'reason': 'round done'}

    monkeypatch.setattr(schedule, 'exec_round', one)
    result = catchup.run(book.root, nights=2)
    assert len(result['nights']) == 2
    assert phases == ['daily-investigation', 'daily-investigation']
    assert len(set(scopes)) == 2


def test_same_person_failed_retry_and_owner_refresh_get_new_nights(book, monkeypatch):
    from connectonion.rem import catchup, same_person
    record = 'people/owner.md'
    book.stub_person(record, 'Casey Reed', ['casey@example.test'], email='casey@example.test')
    write_json(state_path(book.root, 'map.json'), {'owner': {'record': record, 'addresses': ['casey@example.test']}})
    verdict = {}
    attempts = []

    def one(root, **options):
        assert same_person._due(root, verdict)
        assert daily._owner_due(root)
        same_person._failed(root, {'pages': ['people/fern.md', 'people/fern-other.md'], 'why': 'same name'}, ValueError('fixture'))
        verdict.update(read_json(state_path(root, same_person.VERDICTS), {})['people/fern.md|people/fern-other.md'])
        assert not same_person._due(root, verdict)
        monkeypatch.setattr(daily, 'investigate', lambda *a, **kw: {})
        daily._owner(root, daily._owner_due(root)[0], clients={}, subscriptions={})
        assert daily._owner_due(root) == []
        cursor = native_round.prepare(root, read_config(root), scheduled=False)
        cursor['changed'] = ['people/fern.md']
        native_round.finish(root, cursor)
        attempts.append(True)
        return {'outcome': 'done', 'reason': 'round done'}

    monkeypatch.setattr(schedule, 'exec_round', one)
    catchup.run(book.root, nights=2)
    assert len(attempts) == 2
    assert not state_path(book.root, 'owner-refresh.json').exists()
    assert daily._owner_due(book.root), 'a virtual night must not consume the real owner refresh'


def test_translation_attempt_totals_use_each_virtual_night(book, monkeypatch):
    from connectonion.rem import catchup, translate
    counts = []

    def one(root, **options):
        assert translate.attempts_today(root) == 0
        record, path = daily._reserve(root, 'translate', 1, {})
        record.update(outcome='completed', changed=['people/fern.md'])
        write_json(path, record)
        counts.append(translate.attempts_today(root))
        cursor = native_round.prepare(root, read_config(root), scheduled=False)
        cursor['changed'] = ['people/fern.md']
        native_round.finish(root, cursor)
        return {'outcome': 'done', 'reason': 'round done'}

    monkeypatch.setattr(schedule, 'exec_round', one)
    catchup.run(book.root, nights=2)
    assert counts == [1, 1]
    assert translate.attempts_today(book.root) == 0


def test_translation_tail_still_runs_after_daily_call_cap(book, model, monkeypatch):
    from connectonion.rem import translate
    backlog(book, 20)
    set_config(book.root, ['limits.runner_calls_per_day', '1'])
    set_config(book.root, ['languages', 'zh'])
    original, translated = runner.run_task, []

    def run(directory, prompt, config, stage, **options):
        if stage != 'translate':
            return original(directory, prompt, config, stage, **options)
        task = read_json(directory / 'task.json', {})
        prepared = task['task']
        translated.append(task['record'])
        Path(prepared['candidate']).write_text(prepared['prose'])
        return {'result': prepared['prose']}

    monkeypatch.setattr(runner, 'run_task', run)
    result = invoke(book)
    assert result.exit_code == 0, result.output
    assert len(model[0]) == 1
    assert translated and translate.backlog(book.root, 'zh') == []
    assert f'{len(translated)} pages translated' in result.output


def test_interrupted_night_reports_kept_pages_and_next_resumes_its_limits(book, model, monkeypatch):
    backlog(book, 60)
    set_config(book.root, ['limits.abstract_rounds_per_night', '2'])
    original = runner.run_task

    def interrupt(directory, prompt, config, stage, **options):
        if model[0]:
            raise KeyboardInterrupt
        return original(directory, prompt, config, stage, **options)

    monkeypatch.setattr(runner, 'run_task', interrupt)
    result = invoke(book, '--nights', '2')
    assert result.exit_code == 130, result.output
    assert '20 pages written before the stop' in result.output
    assert result.output.rstrip().endswith(f'Next: co rem --root {book.root} exec')
    monkeypatch.setattr(runner, 'run_task', original)
    # CliRunner shares this test process; the stopped terminal's process would have exited.
    monkeypatch.setattr(native, '_alive', lambda pid: False)
    task = native.next_task(book.root)
    output = runner.run_task(Path(task['material']), task['instructions'], read_config(book.root), task['stage'])
    assert native.submit(book.root, task['id'], usage=output.get('usage'))['outcome'] == 'accepted'
    assert native.next_task(book.root)['reason'] == 'round done'
    assert not state_path(book.root, 'abstract-night.json').exists()
    assert len(book.list('decisions')) == 40


def test_daily_retry_and_no_change_cooldowns_get_fresh_nights(book, monkeypatch):
    from connectonion.rem import catchup, leads, refusals
    record = 'people/fern.md'
    counts = []

    def one(root, **options):
        assert not leads.cooling(root, [record])
        leads.remember_no_change(root, record, True)
        assert leads.cooling(root, [record]) == [record]
        if counts:
            assert record in refusals.due_for_retry(root)
            assert record not in refusals.parked_waiting(root)
        refusals.remember_refusal(root, record, ['codex:fixture:1'], 'fixture', stage='investigate', parked=True)
        refusals.mark_retried(root, record)
        assert record not in refusals.due_for_retry(root)
        assert record in refusals.parked_waiting(root)
        cursor = native_round.prepare(root, read_config(root), scheduled=False)
        cursor['changed'] = [record]
        native_round.finish(root, cursor)
        counts.append(True)
        return {'outcome': 'done', 'reason': 'round done'}

    monkeypatch.setattr(schedule, 'exec_round', one)
    catchup.run(book.root, nights=2)
    assert len(counts) == 2


@pytest.mark.parametrize('same_page', [False, True])
def test_imported_and_summarized_session_page_counts_are_exact(book, monkeypatch, same_page):
    from connectonion.rem import catchup

    def one(root, **options):
        cursor = native_round.prepare(root, read_config(root), scheduled=False)
        cursor['sessions'] = {'imported': 1, 'updated': 0, 'changed': ['sessions/imported.md']}
        cursor['changed'] = ['sessions/imported.md' if same_page else 'sessions/summarized.md']
        native_round.finish(root, cursor)
        return {'outcome': 'done', 'reason': 'round done'}

    monkeypatch.setattr(schedule, 'exec_round', one)
    result = catchup.run(book.root)
    assert result['written'] == (1 if same_page else 2)
    assert 'sessions/imported.md' in result['nights'][0]['changed']


@pytest.mark.parametrize('held', ['weekly', 'daily'])
def test_scheduled_takeover_keeps_unfinished_work_when_held(book, monkeypatch, held, rem_clock):
    from connectonion.rem import catchup
    config = read_config(book.root)
    with catchup.scope(book.root, 1):
        cursor = native_round.prepare(book.root, config, scheduled=False)
    cursor.update(jobs=[{'record': 'people/fern.md', 'kind': 'person'}],
                  current={'record': 'people/fern.md', 'draft': 'Unfinished draft'},
                  project_quote={'record': 'projects/fern.md', 'draft': 'Unfinished project'})
    write_json(state_path(book.root, 'round.json'), cursor)
    write_json(state_path(book.root, 'worker.json'), {'enabled': True})
    if held == 'weekly':
        monkeypatch.setattr(quota, 'meter', lambda *a: {'used_percent': 90, 'window_minutes': 10080,
                                                     'resets_at': (rem_clock + timedelta(days=5)).timestamp()})
    else:
        set_config(book.root, ['limits.runner_calls_per_day', '1'])
        daily._reserve(book.root, 'daily-investigation', 1, {})
        # A translation tail exists, but the model boundary stays fake.
        from connectonion.rem import translate
        monkeypatch.setattr(translate, 'languages', lambda root: ['zh'])
        monkeypatch.setattr(translate, 'backlog', lambda *a, **kw: ['people/fern.md'])
        monkeypatch.setattr(native_round, 'prepare_translation', lambda *a: {'stop': 'daily cap reached'})
    native.next_task(book.root, scheduled=True)
    saved = read_json(state_path(book.root, 'round.json'), {})
    assert 'catchup_night' not in saved
    assert saved['slot'] is not None
    assert saved['jobs'][0]['record'] == 'people/fern.md'
    assert saved['current'] == cursor['current']
    assert saved['project_quote'] == cursor['project_quote']


def test_scheduled_pending_work_keeps_its_saved_limit_identity(book, monkeypatch):
    from connectonion.rem import catchup
    write_json(state_path(book.root, 'round.json'), {'catchup_night': 7, 'pending': 'fixture'})

    def inside(root, **options):
        record, _ = daily._reserve(root, 'daily-investigation', 1, {})
        assert record['catchup_night'] == 7
        assert service.daily_cap(root)['used'] == 1
        return {'outcome': 'task'}

    monkeypatch.setattr(native, '_next_task', inside)
    assert native.next_task(book.root, scheduled=True)['outcome'] == 'task'
    assert catchup.number(book.root) is None
    assert service.daily_cap(book.root)['used'] == 0


def test_new_night_keeps_material_needed_by_an_unfinished_page(book, monkeypatch, rem_clock):
    from connectonion.rem import catchup
    with catchup.scope(book.root, 1):
        cursor = native_round.prepare(book.root, read_config(book.root), scheduled=False)
    folder = state_path(book.root, 'tasks/native-fixture')
    folder.mkdir(parents=True)
    plan = folder / 'plan.md'
    plan.write_text('Findings the unfinished page still needs.')
    write_json(folder / 'task.json', {'status': 'accepted', 'round_started_at': cursor['started_at']})
    cursor.update(jobs=[{'record': 'people/fern.md', 'kind': 'person'}],
                  current={'record': 'people/fern.md', 'plan_path': str(plan)})
    monkeypatch.setattr(service, 'now', lambda: rem_clock + timedelta(minutes=1))
    with catchup.scope(book.root, 2):
        native_round.prepare(book.root, read_config(book.root), scheduled=False, carry=cursor)
    runner.scrub_task(folder)
    assert plan.is_file(), 'new-night cleanup must keep the unfinished page material'


@pytest.mark.parametrize('phase,draft', [('reply-draft', None), ('daily-investigation', 'Unfinished notebook prose')])
def test_a_skipped_draft_does_not_count_as_output(book, monkeypatch, phase, draft):
    from connectonion.rem import catchup

    def one(root, **options):
        cursor = native_round.prepare(root, read_config(root), scheduled=False)
        record, path = daily._reserve(root, phase, 1, {})
        record.update(outcome='completed', draft=draft, report='No committed reply draft')
        write_json(path, record)
        native_round.finish(root, cursor)
        return {'outcome': 'done', 'reason': 'round done'}

    monkeypatch.setattr(schedule, 'exec_round', one)
    result = catchup.run(book.root, nights=2)
    assert result['drafts'] == 0
    assert len(result['nights']) == 1


def test_catchup_help_is_discoverable_and_plain():
    root = CliRunner().invoke(app, ['rem', '--help'])
    shown = CliRunner().invoke(app, ['rem', 'catchup', '--help'])
    assert shown.exit_code == 0, shown.output
    assert 'catchup' in root.output
    assert 'co rem catchup [--nights N]' in shown.output
    assert "Do the night's work, then one deepen slot." in shown.output
    assert 'A night with deepen can take an hour or more.' in shown.output
    assert 'Example:  co rem catchup  |  co rem catchup --nights 5' in shown.output
    assert '--nights N (default 1)' in shown.output
    assert 'quota floor' in shown.output
    assert 'Calls the configured model' in shown.output
    assert 'Schedule times stay the same.' in shown.output
    assert 'Next:     co rem open' in shown.output
    decisions = CliRunner().invoke(app, ['rem', 'abstract', '--help'])
    assert 'Saves progress for the next run.' in decisions.output and 'decisions, knowledge, and principles' in decisions.output
    assert 'Shares progress with the night' not in decisions.output


@pytest.mark.parametrize('value', ['0', '-1', 'no'])
def test_invalid_nights_does_not_start_work(book, model, value):
    result = invoke(book, '--nights', value)
    assert result.exit_code == 2
    assert not model[0]


def test_json_reports_nights_and_next_command(book, model):
    backlog(book, 40)
    result = invoke(book, '--nights', '2', json_out=True)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data['ok'] and len(data['data']['nights']) == 2
    assert data['data']['written'] == 40
    assert data['next'] == f'co rem --root {book.root} open'


def test_catchup_reports_exec_depth_without_own_slot(book, monkeypatch):
    from connectonion.rem import catchup
    calls = []
    def execute(root, **options):
        calls.append(catchup.number(root))
        write_json(state_path(root, 'round.json'), {'catchup_night': catchup.number(root),
                   'changed': ['people/person.md']})
        return {'outcome': 'done', 'reason': 'round done', 'depth': {
            'stopped': '', 'rounds': [{'record': 'people/person.md', 'enrich': 'completed', 'muse': 'completed'}]}}
    monkeypatch.setattr(schedule, 'exec_round', execute)
    monkeypatch.setattr(depth, 'slot', lambda *a, **k: pytest.fail('catchup called a second slot'))
    result = catchup.run(book.root, nights=2)
    assert len(calls) == 2 and result['deepened'] == 2
    assert [row['deepened'] for row in result['nights']] == [1, 1]
