"""Five named stages; whole-round launchers own exactly one deepen slot."""
import json
from subprocess import CompletedProcess

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import codex_exec, depth, native, runner, schedule, service
from connectonion.rem.config import prepare, set_config
from connectonion.rem.files import Notebook, read_json, state_path, write_json

pytestmark = pytest.mark.usefixtures('rem_clock')


def completed_cursor(root, *, phase='daily-investigation', done=True):
    cursor = {'phase': phase, 'done': done, 'changed': ['projects/fern.md'],
              'started_at': service.now().isoformat(), 'translated': 1}
    write_json(state_path(root, 'round.json'), cursor)
    return cursor


@pytest.mark.parametrize('scheduled', [False, True])
def test_exec_deepens_once_after_all_round_work(tmp_path, monkeypatch, scheduled):
    prepare(tmp_path)
    events = []
    tasks = iter([{'outcome': 'task', 'id': 'one', 'stage': 'abstract',
                   'instructions': 'fixture', 'material': str(tmp_path)},
                  {'outcome': 'task', 'id': 'two', 'stage': 'translate',
                   'instructions': 'fixture', 'material': str(tmp_path)},
                  {'outcome': 'done', 'reason': 'round done'}])

    def next_task(root, **options):
        task = next(tasks)
        if task['outcome'] == 'done':
            completed_cursor(root)
        return task

    monkeypatch.setattr(native, 'next_task', next_task)
    monkeypatch.setattr(native, 'submit', lambda *a, **k: {'outcome': 'accepted'})
    monkeypatch.setattr(runner, 'run_task', lambda *a, **k: events.append(a[-1]) or {})
    monkeypatch.setattr('connectonion.rem.codex_schedule.CodexNative.recent_desktop_fire', lambda *a: False)
    monkeypatch.setattr(depth, 'slot', lambda *a, **k: events.append('deepen') or {'rounds': [], 'stopped': ''})
    result = schedule.exec_round(tmp_path, scheduled=scheduled)
    assert events == ['abstract', 'translate', 'deepen']
    assert result['depth'] == {'rounds': [], 'stopped': ''}


@pytest.mark.parametrize('outcome,reason,phase', [
    ('refused', 'candidate rejected', 'daily-investigation'),
    ('busy', 'maintenance busy', 'daily-investigation'),
    ('done', 'Codex quota floor reached', 'daily-investigation'),
    ('done', 'not due', 'daily-investigation'),
    ('done', 'round done', 'daily-translation'),
])
def test_exec_does_not_deepen_early_stops_or_translation_only(tmp_path, monkeypatch, outcome, reason, phase):
    prepare(tmp_path)
    completed_cursor(tmp_path, phase=phase)
    monkeypatch.setattr(native, 'next_task', lambda *a, **k: {'outcome': outcome, 'reason': reason})
    monkeypatch.setattr(depth, 'slot', lambda *a, **k: pytest.fail('unexpected deepen'))
    assert schedule.exec_round(tmp_path, scheduled=False)['reason'] == reason


@pytest.mark.parametrize('code,done,phase,expected', [
    (0, True, 'daily-investigation', 1), (1, True, 'daily-investigation', 0),
    (0, False, 'daily-investigation', 0), (0, True, 'daily-translation', 0),
])
def test_codex_launcher_deepens_only_after_a_completed_whole_round(tmp_path, monkeypatch, code, done, phase, expected):
    prepare(tmp_path)
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
    monkeypatch.setattr(codex_exec, '_reap_orphan_maintenance', lambda *a: [])
    monkeypatch.setattr('connectonion.rem.codex_schedule.CodexNative.recent_desktop_fire', lambda *a: False)
    calls = []
    monkeypatch.setattr(depth, 'slot', lambda *a, **k: calls.append('deepen') or {'rounds': [], 'stopped': ''})

    def run(command, **options):
        completed_cursor(tmp_path, done=done, phase=phase)
        return CompletedProcess(command, code)

    codex_exec.run_turn(tmp_path, run=run)
    assert calls == ['deepen'] * expected


def test_codex_launcher_does_not_repeat_a_previously_finished_round(tmp_path, monkeypatch):
    prepare(tmp_path)
    completed_cursor(tmp_path)
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
    monkeypatch.setattr(codex_exec, '_reap_orphan_maintenance', lambda *a: [])
    monkeypatch.setattr('connectonion.rem.codex_schedule.CodexNative.recent_desktop_fire', lambda *a: False)
    monkeypatch.setattr(depth, 'slot', lambda *a, **k: pytest.fail('repeated deepen'))
    assert codex_exec.run_turn(tmp_path, run=lambda *a, **k: CompletedProcess(a, 0)) == 'completed'


@pytest.fixture
def stage_book(tmp_path):
    prepare(tmp_path)
    set_config(tmp_path, ['schedule.timezone', 'UTC', 'languages', 'zh,en'])
    book = Notebook(tmp_path)
    book.stub_project('projects/fern.md', 'Fern', ['/fictional/fern'])
    book.write('people/avery.md', '# Avery\n\nA colleague.\n')
    book.write('sessions/choices.md', '# Choices\n\n## Decisions\n- “Keep the simple path.” [1]\n'
               '\n## Sources\n- [1] codex:fictional:7\n')
    write_json(state_path(tmp_path, 'progress.json'), {'gmail': {'pending': {'inbox': [{}, {}]}}})
    sources = service.subscriptions(tmp_path)
    sources['gmail'] = {'kind': 'gmail', 'enabled': True, 'consented': True}
    write_json(state_path(tmp_path, 'subscriptions.json'), sources)
    for i, phase in enumerate(['sync', 'daily-investigation', 'enrich', 'abstract', 'daily-translation'], 1):
        write_json(state_path(tmp_path, f'runs/run_{i}.json'), {
            'id': f'run_{i}', 'phase': phase, 'outcome': 'completed', 'runner_attempts': 0,
            'started_at': f'2026-11-0{i}T10:00:00+00:00', 'changed': [], 'items': int(phase == 'sync')})
    return tmp_path


def test_status_five_stages_match_json_and_saved_queues(stage_book, monkeypatch):
    monkeypatch.setattr(runner, 'run_task', lambda *a, **k: pytest.fail('status ran model'))
    cli = CliRunner()
    args = ['rem', '--root', str(stage_book)]
    result = cli.invoke(app, [*args, 'status'])
    assert result.exit_code == 0, result.output
    expected = [
        'Collect: 2 listed mail waiting; last ran 2026-11-01',
        'Investigate: 1 page waiting; last ran 2026-11-02',
        'Deepen: 2 pages waiting; last ran 2026-11-03',
        'Abstract: 1 captured decision waiting; last ran 2026-11-04; 0 decisions · 0 knowledge · 0 principles',
        'Translate: 3 page translations waiting; last ran 2026-11-05',
    ]
    lines = result.stdout.splitlines()
    first = lines.index(expected[0])
    # Status stays 80 columns wide: the Abstract sentence breaks after a `;`, its page counts two spaces in.
    assert lines[first:first + 6] == [*expected[:3], 'Abstract: 1 captured decision waiting; last ran 2026-11-04;',
                                      '  0 decisions · 0 knowledge · 0 principles', expected[4]]
    assert 'Notebook' in result.stdout and 'Today' in result.stdout
    raw = cli.invoke(app, [*args, '--json', 'status'])
    assert raw.exit_code == 0, raw.output
    stages = json.loads(raw.stdout)['data']['stages']
    assert [row['name'] for row in stages] == ['Collect', 'Investigate', 'Deepen', 'Abstract', 'Translate']
    assert [row['waiting'] for row in stages] == [2, 1, 2, 1, 3]
    assert [row['last_run'] for row in stages] == [f'2026-11-0{i}' for i in range(1, 6)]
    assert [row['text'] for row in stages] == expected


def test_status_stages_never_run_and_native_abstract_date(tmp_path):
    prepare(tmp_path)
    stages = service.status(tmp_path)['stages']
    assert len(stages) == 5 and all(row['last_run'] is None for row in stages)
    assert all('last ran never' in row['text'] for row in stages)
    write_json(state_path(tmp_path, 'runs/run_native.json'), {'id': 'run_native',
        'phase': 'daily-update', 'stage': 'abstract', 'outcome': 'completed',
        'started_at': '2026-11-08T23:45:00+00:00'})
    set_config(tmp_path, ['schedule.timezone', 'Australia/Sydney'])
    assert service.status(tmp_path)['stages'][3]['last_run'] == '2026-11-09'


def test_catchup_cap_does_not_deepen_an_unfinished_round(tmp_path, monkeypatch):
    from connectonion.rem import catchup
    prepare(tmp_path)
    completed_cursor(tmp_path, done=False)
    monkeypatch.setattr(native, 'next_task', lambda *a, **k: {'outcome': 'done', 'reason': 'daily cap reached'})
    monkeypatch.setattr(depth, 'slot', lambda *a, **k: pytest.fail('deepened unfinished capped round'))
    with catchup.scope(tmp_path, 1):
        cursor = completed_cursor(tmp_path, done=False)
        write_json(state_path(tmp_path, 'round.json'), {**cursor, 'catchup_night': 1})
        assert 'depth' not in schedule.exec_round(tmp_path, scheduled=False)


def test_codex_launcher_records_a_failed_deepen_slot(tmp_path, monkeypatch):
    prepare(tmp_path)
    monkeypatch.setattr(codex_exec, '_start_command', lambda *a: ['fictional-codex'])
    monkeypatch.setattr(codex_exec, '_reap_orphan_maintenance', lambda *a: [])
    monkeypatch.setattr('connectonion.rem.codex_schedule.CodexNative.recent_desktop_fire', lambda *a: False)
    def broken_slot(*args, **kwargs):
        raise RuntimeError('fixture slot failed')
    monkeypatch.setattr(depth, 'slot', broken_slot)
    def run(command, **options):
        completed_cursor(tmp_path)
        return CompletedProcess(command, 0)
    with pytest.raises(RuntimeError, match='fixture slot failed'):
        codex_exec.run_turn(tmp_path, run=run)
    assert read_json(state_path(tmp_path, 'last-turn.json'), {})['result'] == 'failed'


def test_finishing_deepen_preserves_a_newer_round(tmp_path, monkeypatch):
    prepare(tmp_path)
    completed_cursor(tmp_path)
    newer = {'started_at': '2026-11-15T11:00:00+00:00', 'pending': 'new-task', 'done': False}
    def slot(*args, **kwargs):
        write_json(state_path(tmp_path, 'round.json'), newer)
        return {'rounds': [], 'stopped': ''}
    monkeypatch.setattr(depth, 'slot', slot)
    result = schedule.finish_exec(tmp_path, {'outcome': 'done', 'reason': 'round done'})
    assert result['depth'] == {'rounds': [], 'stopped': ''}
    assert read_json(state_path(tmp_path, 'round.json'), {}) == newer


def test_status_dates_native_abstract_claim_audits(tmp_path):
    prepare(tmp_path)
    write_json(state_path(tmp_path, 'runs/run_audit.json'), {'id': 'run_audit',
        'phase': 'daily-update', 'stage': 'claim-audit', 'render_stage': 'abstract',
        'outcome': 'completed', 'started_at': '2026-11-08T10:00:00+00:00'})
    stages = service.status(tmp_path)['stages']
    assert stages[3]['last_run'] == '2026-11-08'
    assert stages[1]['last_run'] is None


def test_investigate_waiting_includes_pages_with_same_person_checks(tmp_path):
    from connectonion.rem import same_person
    prepare(tmp_path)
    book = Notebook(tmp_path)
    for record, title, address in [('people/robin.md', 'Robin', 'robin@mail.example'),
                                   ('people/robin-hale.md', 'Robin Hale', 'rhale@work.example')]:
        book.stub_person(record, title, [address], email=address)
        book.write(record, f'# {title}\n\n## Identity\n- Email: {address}\n')
    assert len(same_person.candidates(tmp_path)) == 1
    assert service.status(tmp_path)['stages'][1]['waiting'] == 2


def test_investigate_waiting_includes_pages_awaiting_reply_preparation(tmp_path, monkeypatch):
    from connectonion.rem import night
    prepare(tmp_path)
    monkeypatch.setattr(night, 'summary', lambda root: {'unprepared': [{'record': 'people/avery.md'}]})
    assert service.status(tmp_path)['stages'][1]['waiting'] == 1


def test_status_stages_accept_owner_metadata_without_a_page(tmp_path):
    prepare(tmp_path)
    write_json(state_path(tmp_path, 'map.json'), {'owner': {'addresses': ['owner@example.test'],
                                                          'name': 'Fictional Owner'}})
    assert len(service.status(tmp_path)['stages']) == 5


@pytest.mark.parametrize('phase', ['daily-investigation', 'daily-update'])
def test_collect_date_includes_native_round_batch_and_ignores_empty_runs(stage_book, phase):
    write_json(state_path(stage_book, 'runs/run_native.json'), {
        'id': 'run_native', 'phase': phase, 'native_round': True, 'outcome': 'pending',
        'started_at': '2026-11-09T23:30:00+00:00',
        'batch': {'phase': 'sync', 'started_at': '2026-11-11T23:30:00+00:00',
                  'items': 40, 'items_by_source': {'gmail': 40}, 'outcome': 'completed'}})
    write_json(state_path(stage_book, 'runs/run_empty.json'), {
        'id': 'run_empty', 'phase': 'sync', 'outcome': 'completed', 'items': 0,
        'started_at': '2026-11-14T12:00:00+00:00'})
    set_config(stage_book, ['schedule.timezone', 'Australia/Sydney'])
    assert service.status(stage_book)['stages'][0]['last_run'] == '2026-11-12'


def test_collect_count_distinguishes_disabled_and_unapproved_sources(stage_book):
    sources = service.subscriptions(stage_book)
    sources.update(outlook={'kind': 'outlook', 'enabled': False, 'consented': True},
                   other={'kind': 'gmail', 'enabled': True, 'consented': False})
    write_json(state_path(stage_book, 'subscriptions.json'), sources)
    progress = read_json(state_path(stage_book, 'progress.json'), {})
    progress.update(outlook={'pending': {'someone': [{}, {}, {}]}},
                    other={'pending': {'someone': [{}]}})
    write_json(state_path(stage_book, 'progress.json'), progress)
    row = service.status(stage_book)['stages'][0]
    assert row['waiting'] == 2 and row['held'] == 4
    assert '2 listed mail waiting' in row['text'] and '4 held (source disabled or unapproved)' in row['text']


def test_native_mail_slot_preserves_latest_nonempty_batch_receipt(stage_book, monkeypatch):
    from datetime import datetime, timezone
    from connectonion.rem import native_round
    from connectonion.rem.config import read_config
    old = {'items': 10, 'started_at': '2026-11-09T12:00:00+00:00'}
    new = {'items': 40, 'started_at': '2026-11-11T12:00:00+00:00'}
    records = iter([new, {'items': 0, 'started_at': '2026-11-12T12:00:00+00:00'}])
    monkeypatch.setattr(native_round, '_read_sources', lambda *a: {'done': True, 'record': next(records)})
    cursor = {'run': {'id': 'run_native', 'phase': 'daily-update', 'native_round': True,
                     'outcome': 'pending', 'started_at': old['started_at'], 'batch': old}}
    for day in (11, 12):
        native_round.read_new_mail(stage_book, cursor, read_config(stage_book),
                                  datetime(2026, 11, day, 12, tzinfo=timezone.utc))
    saved = read_json(state_path(stage_book, 'runs/run_native.json'), {})
    assert saved['batch'] == new
    assert service.status(stage_book)['stages'][0]['last_run'] == '2026-11-11'
