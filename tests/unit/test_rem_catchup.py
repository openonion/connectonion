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
        assert stage.removesuffix(' (repair)') == 'abstract', stage
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
    monkeypatch.setattr(calendar, 'calendar_events', lambda *args: (calls.append(args) or [], {'read': 1, 'left_out': {}}))
    result = invoke(book, '--nights', '2', json_out=True)
    assert result.exit_code == 0, result.output
    rows = json.loads(result.stdout)['data']['nights']
    assert len(calls) == len(rows) == 2
    assert all({k: v for k, v in row['calendar'].items() if k not in ('day_plan', 'todos')} ==
               {'events': 0, 'read': ['google'], 'errors': {}, 'capped': []} for row in rows)
    assert all(row['day_plan'] == row['calendar']['day_plan'] for row in rows)
    assert all(row['day_plan']['dates'] == ['2026-09-07', '2026-09-08'] for row in rows)


def test_catchup_prints_calendar_result_in_each_night(book, model, monkeypatch):
    from connectonion.rem import calendar
    backlog(book, 20)
    monkeypatch.setattr(calendar, 'available', lambda kind: kind == 'google')
    monkeypatch.setattr(calendar, 'calendar_events', lambda *args: ([], {'read': 1, 'left_out': {}}))
    result = invoke(book)
    assert result.exit_code == 0, result.output
    assert '0 calendar events saved' in next(line for line in result.stdout.splitlines() if line.startswith('Night 1:'))
    assert 'day plan saved for 2026-09-07 and 2026-09-08' in result.stdout


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
    assert 'Night 1: 0 mail read · 0 sessions read · 20 pages written (20 of them decisions) · 0 pages translated' in result.output
    assert 'Night 2: 0 mail read · 0 sessions read · 20 pages written (20 of them decisions) · 0 pages translated' in result.output
    assert 'Done: 2 nights · 40 pages written (40 of them decisions) · 0 pages translated' in result.output
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


def test_a_page_whose_enrich_failed_is_counted_as_not_deepened_with_a_short_cause(book, model, monkeypatch):
    backlog(book, 20)
    book.write('people/person.md', '# Person\n')

    def fail(*args, **options):
        raise runner.RunFailed('fixture stage failed', {'input_tokens': 10})

    for name in ('enrich', 'muse'):
        monkeypatch.setattr(depth.muse, name, fail)
    result = invoke(book)
    assert result.exit_code == 0, result.output
    for prefix in ('Night 1:', 'Done:'):
        line = next(line for line in result.stdout.splitlines() if line.startswith(prefix))
        assert '0 pages deepened · 1 not deepened (enrich failed: fixture stage failed; see co rem logs)' in line


def test_the_night_line_gives_a_refused_enrich_in_a_few_words_without_the_refusal_text_or_a_path(book, model, monkeypatch):
    """2026-11-16: the parenthesis after "pages deepened" was 200 characters of raw refusal,
    a task path included, and the refused page was counted as deepened."""
    backlog(book, 20)
    for name in ('one', 'two', 'three'):
        book.write(f'people/{name}.md', f'# {name.title()}\n')

    def enrich(root, record, **options):
        if record == 'people/two.md':
            raise runner.RunFailed(
                f'Candidate rejected, kept at {root}/.state/tasks/enrich-1/candidate.md: Research captures need an '
                'HTTP(S) URL or a native read-only source ID: entry 2 of web/sources.json (file notes.md) has '
                '"file:notes.txt"; write the page\'s exact address', {'input_tokens': 10})
        return {}

    monkeypatch.setattr(depth.muse, 'enrich', enrich)
    result = invoke(book)
    assert result.exit_code == 0, result.output
    line = next(line for line in result.stdout.splitlines() if line.startswith('Night 1:'))
    assert ('2 pages deepened · 1 not deepened (enrich refused: Research captures need an HTTP(S) URL or a native '
            'read-only source ID; see co rem logs)') in line
    assert str(book.root) not in line and 'entry 2' not in line


def test_a_round_saved_before_causes_were_kept_gives_its_first_clause(tmp_path):
    from connectonion.rem import catchup
    rounds = [{'record': 'people/one.md', 'enrich': 'failed: Research captures need a URL: entry 2 of web/sources.json',
               'muse': 'completed'},
              {'record': 'people/two.md', 'enrich': 'completed', 'muse': 'refused'}]
    counts = catchup._depth_counts(tmp_path, {'rounds': rounds, 'stopped': ''}, {})
    assert counts == {'deepened': 1, 'deepen_reason': 'people/two.md: enrich completed, muse refused',
                      'not_deepened': 1, 'not_deepened_reason': 'enrich failed: Research captures need a URL'}


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
        model[1].extend(['empty', 'empty'])
    result = invoke(book, '--nights', '5')
    # An answer refused twice is parked, not a failed round: the night ends in words, exit 0.
    assert result.exit_code == 0, result.output
    assert 'Night 1:' in result.output and 'Night 2:' not in result.output
    assert 'Stopped: night 1 produced nothing' in result.output
    assert len(model[0]) == 2 * int(empty_model)
    assert ('1 page parked (a task: refused twice for the same reason: ' in result.output) == empty_model


@pytest.mark.parametrize('between', [False, True])
def test_quota_floor_stops_with_plain_reason(book, model, monkeypatch, rem_clock, between):
    backlog(book, 60)
    meter = {'used_percent': 90, 'resets_at': (rem_clock + timedelta(days=5)).timestamp(), 'window_minutes': 10080}
    monkeypatch.setattr(quota, 'meter', lambda *a: {'unknown': 'fixture'} if between and not model[0] else meter)
    reason = quota.floor_block(meter, read_config(book.root)['limits'])
    result = invoke(book, '--nights', '3')
    assert result.exit_code == 0, result.output
    assert f'Stopped: {reason}' in result.output
    assert len(model[0]) == int(between)
    assert len(book.list('decisions')) == 20 * int(between)
    assert result.output.rstrip().endswith(f'Next: co rem --root {book.root} open')


def test_a_spent_investigation_budget_holds_investigation_and_the_night_still_abstracts_and_deepens(
        book, model, monkeypatch, rem_clock):
    """2026-11-16: the night ended at "investigation has used 35 of its 35-point weekly budget";
    Abstract, Translate and Deepen did not run though the Codex week was at 37%."""
    backlog(book, 60)
    book.write('people/person.md', '# Person\n')
    meter = {'used_percent': 37, 'resets_at': (rem_clock + timedelta(days=5)).timestamp(), 'window_minutes': 10080}
    monkeypatch.setattr(quota, 'meter', lambda *a: meter)
    monkeypatch.setattr(quota, 'points_spent', lambda *a, **k: 35)
    monkeypatch.setattr(native_round, '_jobs', lambda *a, **k: [{'record': 'people/person.md', 'kind': 'person'}])
    monkeypatch.setattr(native_round, '_prepare_job', lambda *a: pytest.fail('a page was started past the budget'))
    slots = []
    monkeypatch.setattr(depth, 'slot', lambda *a, **k: slots.append(1) or {'rounds': [], 'stopped': ''})
    result = invoke(book, '--nights', '2')
    assert result.exit_code == 0, result.output
    assert len(model[0]) == 2 and len(book.list('decisions')) == 40 and len(slots) == 2
    for number in (1, 2):
        line = next(line for line in result.stdout.splitlines() if line.startswith(f'Night {number}:'))
        assert '(20 of them decisions)' in line and 'exec stopped' not in line
        assert re.search(r'investigation is waiting for its weekly budget \(35 of 35 points used; '
                         r'the Codex week resets \w{3} \d{2} \w{3} \d{2}:\d{2}\); 1 page waits', line), line
    assert 'Stopped:' not in result.stdout
    assert not state_path(book.root, 'round-held.json').exists()


def test_the_budget_is_read_before_every_task_so_one_reached_mid_night_holds_the_pages_not_started(
        book, monkeypatch, rem_clock):
    meter = {'used_percent': 37, 'resets_at': (rem_clock + timedelta(days=5)).timestamp(), 'window_minutes': 10080}
    config, cursor, spent = read_config(book.root), {}, [34, 35, 0]
    monkeypatch.setattr(quota, 'points_spent', lambda *a, **k: spent.pop(0))
    native._hold_investigation(book.root, cursor, config, meter)
    assert 'investigation_held' not in cursor
    native._hold_investigation(book.root, cursor, config, meter)
    assert cursor['investigation_held']['reason'].startswith('investigation is waiting for its weekly budget (35 of 35')
    # The week reset: the next task's reading lifts the hold.
    native._hold_investigation(book.root, cursor, config, meter)
    assert 'investigation_held' not in cursor


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
    assert "Do the night's work, including its one deepen slot." in shown.output
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


MAIL = [{'role': 'user', 'source': 'gmail:fixture:1', 'timestamp': '2026-09-07T10:00:00Z',
         'speaker': 'wren@example.test', 'text': 'Can we move the pilot review to Friday?'},
        {'role': 'user', 'source': 'gmail:fixture:2', 'timestamp': '2026-09-07T11:00:00Z',
         'speaker': 'wren@example.test', 'text': 'Friday at ten works for the whole team.'}]
WAITING = ['Investigate', 'Deepen', 'Abstract', 'Translate']


@pytest.fixture
def held(book, monkeypatch, rem_clock):
    """A notebook whose Codex week is at its floor, with fake mail and calendar clients and no model."""
    from connectonion.rem import calendar
    reads, events = [], []
    week = {'used_percent': 99, 'window_minutes': 10080, 'resets_at': (rem_clock + timedelta(days=2)).timestamp()}

    def fetch(root, selected, progress, config, *args, **kwargs):
        reads.append(sorted(selected))
        return {'done': False, 'items': MAIL, 'updated': {**progress, 'gmail': {'scanned_until': 'x'}},
                'record': {'extracted': False, 'id': 'run_' + 'b' * 32, 'items': 2, 'items_by_source': {'gmail': 2}},
                'kind': 'gmail', 'leads': [None], 'digested': None}

    monkeypatch.setattr(quota, 'meter', lambda *a: week)
    monkeypatch.setattr(service, 'prepare_sync', fetch)
    monkeypatch.setattr(calendar, 'available', lambda kind: kind == 'google')
    monkeypatch.setattr(calendar, 'calendar_events', lambda *args: (events.append(args) or [], {'read': 1, 'left_out': {}}))
    monkeypatch.setattr(runner, 'run_task', lambda *a, **k: pytest.fail('a held catchup called the model'))
    monkeypatch.setattr(depth, 'slot', lambda *a, **k: pytest.fail('a held catchup started deepen'))
    return {'reads': reads, 'events': events, 'reason': quota.floor_block(week, read_config(book.root)['limits'])}


def test_at_the_floor_catchup_still_collects_mail_and_saves_the_calendar_and_day_plan(book, held):
    result = invoke(book, '--nights', '3')
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert len(held['reads']) == 1 and len(held['events']) == 1
    assert 'Done:' not in result.stdout and not any(line.startswith('Night ') for line in lines)
    assert lines[0] == 'No night ran: a limit holds the model, so only the steps that need no model were done.'
    assert lines[1] == ('Collect: 2 mail collected · 0 sessions read · 0 pages updated; '
                        'reading them into pages waits for the model')
    assert lines[2] == 'Calendar: 0 calendar events saved · day plan saved for 2026-09-07 and 2026-09-08'
    assert lines[3] == 'Waiting: Investigate, Deepen, Abstract and Translate call the model'
    assert lines[4] == f"Stopped: {held['reason']}"
    assert 'resumes when it resets' in lines[4]
    cursor = read_json(state_path(book.root, 'round.json'), {})
    assert cursor['batch']['items'] == MAIL and not cursor['batch']['done'] and not cursor.get('pending')
    assert read_json(state_path(book.root, 'catchup.json'), {}) == {}, 'a held catchup must not spend a night'


def test_held_catchup_json_names_what_ran_and_what_waits(book, held, rem_clock):
    result = invoke(book, json_out=True)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)['data']
    assert data['nights'] == [] and data['reason'] == held['reason'] and not data['failed']
    ran = data['held']
    assert (ran['mail'], ran['sessions'], ran['written'], ran['note']) == (2, 0, 0, '')
    assert ran['calendar']['read'] == ['google'] and ran['day_plan']['dates'] == ['2026-09-07', '2026-09-08']
    assert ran['waiting'] == WAITING
    assert ran['resumes_at'].startswith((rem_clock + timedelta(days=2)).date().isoformat())


def test_a_second_held_catchup_keeps_the_waiting_mail_and_saves_the_calendar_again(book, held):
    invoke(book)
    result = invoke(book)
    assert result.exit_code == 0, result.output
    assert len(held['reads']) == 1, 'mail already collected and unread was fetched again'
    assert len(held['events']) == 2
    assert 'Collect: the mail collected earlier still waits to be read into pages' in result.stdout


def test_the_schedule_reads_the_mail_a_held_catchup_collected(book, held, monkeypatch):
    invoke(book)
    assert len(held['reads']) == 1
    write_json(state_path(book.root, 'worker.json'), {'enabled': True})
    task = native.next_task(book.root, scheduled=True)
    assert task['outcome'] == 'task' and task['stage'] == 'maintain', task
    assert len(held['reads']) == 1


def test_a_night_that_ran_before_the_floor_is_not_followed_by_held_work(book, model, monkeypatch, rem_clock):
    backlog(book, 60)
    week = {'used_percent': 95, 'window_minutes': 10080, 'resets_at': (rem_clock + timedelta(days=2)).timestamp()}
    monkeypatch.setattr(quota, 'meter', lambda *a: week if model[0] else {'unknown': 'fixture'})
    result = invoke(book, '--nights', '3', json_out=True)
    data = json.loads(result.stdout)['data']
    assert len(data['nights']) == 1 and data['held'] is None


def test_a_held_catchup_reads_new_mail_into_a_round_whose_batch_was_read(book, held):
    invoke(book)
    path = state_path(book.root, 'round.json')
    cursor = read_json(path, {})
    cursor['batch']['done'] = True
    write_json(path, cursor)
    result = invoke(book)
    assert result.exit_code == 0, result.output
    assert len(held['reads']) == 2
    assert 'Collect: 2 mail collected; reading them into pages waits for the model' in result.stdout
    saved = read_json(path, {})
    assert saved['started_at'] == cursor['started_at'] and not saved['batch']['done']


def test_a_held_catchup_leaves_an_open_task_alone(book, held):
    invoke(book)
    path = state_path(book.root, 'round.json')
    write_json(path, {**read_json(path, {}), 'pending': 'native-fixture'})
    result = invoke(book)
    assert result.exit_code == 0, result.output
    assert len(held['reads']) == 1 and len(held['events']) == 2
    assert 'Collect: task native-fixture is open; its round keeps the mail it collected' in result.stdout


def test_decisions_are_said_as_part_of_the_pages_written_not_beside_them(book, model, monkeypatch):
    """2026-11-16: "81 pages written · 66 decisions written" read as 147 pages; the 66 are among the 81."""
    backlog(book, 2)
    exec_round = schedule.exec_round

    def execute(root, **options):
        result = exec_round(root, **options)
        cursor = read_json(state_path(root, 'round.json'), {})
        cursor['changed'] = [*cursor.get('changed', []), 'people/person.md']
        write_json(state_path(root, 'round.json'), cursor)
        return result

    monkeypatch.setattr(schedule, 'exec_round', execute)
    result = invoke(book)
    assert result.exit_code == 0, result.output
    for prefix in ('Night 1:', 'Done: 1 night'):
        line = next(line for line in result.stdout.splitlines() if line.startswith(prefix))
        assert '3 pages written (2 of them decisions) · ' in line and 'decisions written' not in line


def test_a_night_with_no_decision_pages_says_only_the_pages_written(book, monkeypatch):
    monkeypatch.setattr(schedule, 'exec_round', lambda root, **options: {'outcome': 'done', 'reason': 'round done'})
    result = invoke(book)
    line = next(line for line in result.stdout.splitlines() if line.startswith('Night 1:'))
    assert '0 pages written · 0 pages translated' in line


def test_catchup_says_another_run_holds_the_notebook_and_counts_no_night(book, model):
    """2026-11-17: catchup and the 01:00 scheduled turn ran on one notebook at once and each lost a task."""
    import fcntl
    backlog(book, 20)
    lock = state_path(book.root, 'exec-turn.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = invoke(book)
    assert result.exit_code == 1, result.output
    assert 'Another REM run holds this notebook' in result.output and 'No night was counted' in result.output
    assert 'Night 1' not in result.output and 'Traceback' not in result.output
    assert not model[0] and not state_path(book.root, 'catchup.json').exists()


def test_catchup_holds_the_turn_lock_for_its_rounds_and_releases_it(book, model, monkeypatch):
    from connectonion.rem import codex_exec
    backlog(book, 20)
    seen, run_task = [], runner.run_task

    def run(directory, prompt, config, stage, **options):
        seen.append(codex_exec.run_turn(book.root, run=lambda *a, **kw: pytest.fail('a second turn started')))
        return run_task(directory, prompt, config, stage, **options)

    monkeypatch.setattr(runner, 'run_task', run)
    assert invoke(book).exit_code == 0
    assert seen == ['busy']
    with codex_exec.round_lock(book.root):  # released: the next run takes it
        assert schedule.exec_round(book.root, scheduled=False)['outcome'] != 'busy'


def test_exec_round_is_busy_while_another_run_holds_the_notebook(book, model):
    from connectonion.rem import codex_exec
    backlog(book, 20)

    def run(command, **kwargs):
        assert schedule.exec_round(book.root, scheduled=True) == {'outcome': 'busy', 'reason': codex_exec.BUSY}
        return __import__('subprocess').CompletedProcess(command, 0)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(codex_exec, '_start_command', lambda root, last: ['fictional-codex'])
    monkeypatch.setattr('connectonion.rem.codex_schedule.CodexNative.recent_desktop_fire', lambda self, root: False)
    try:
        assert codex_exec.run_turn(book.root, run=run) == 'completed'
    finally:
        monkeypatch.undo()
    assert not model[0]


def test_scheduled_turn_says_another_run_holds_the_notebook_and_exits_zero(book, capsys):
    import fcntl
    from connectonion.rem import codex_exec
    lock = state_path(book.root, 'exec-turn.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert codex_exec.fire(book.root) == 0
    assert 'Another REM run holds this notebook' in capsys.readouterr().out
