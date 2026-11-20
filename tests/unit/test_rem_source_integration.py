"""Public REM paths use synthetic source hooks without importing any real SDK."""

from datetime import datetime, timedelta, timezone
from threading import Event, Lock, Thread

import pytest
from typer.testing import CliRunner

from connectonion.rem import service, source_hooks as hooks
from connectonion.rem.files import RemError, maintenance_lock, read_json, state_path, write_json
from tests.unit.rem_source_fixtures import citation, shared_sources


def test_source_subcommands_are_reachable_and_auditable_from_help():
    from connectonion.cli import audit
    from connectonion.cli.main import app
    runner = CliRunner()
    paths = ['co', 'co rem', 'co rem sources']
    paths += ['co rem sources ' + name for name in ('add', 'connect', 'remove')]
    found = {}
    for path in paths:
        result = runner.invoke(app, [*path.split()[1:], '--help'], terminal_width=200)
        assert result.exit_code == 0, (path, result.output)
        found[path] = audit.Page(result.exit_code, result.stdout)
    assert 'rem' in audit.listed_commands(found['co'].text)
    assert 'sources' in audit.listed_commands(found['co rem'].text)
    assert set(audit.listed_commands(found['co rem sources'].text)) == {'add', 'connect', 'remove'}
    for path in paths[2:]:
        assert audit.check(path, found[path], found) == [], path


def test_cli_configuration_delegates_options_and_clears_approval(shared_sources):
    from connectonion.cli.main import app
    env = shared_sources
    runner = CliRunner()
    result = runner.invoke(app, ['rem', '--root', str(env.root), 'sources', 'add', 'notes',
                                 '--vault', '/synthetic/Vault', '--folder', 'Work'])
    assert result.exit_code == 0, result.output
    assert 'start' in result.output
    assert not hooks.approved(env.root, 'notes')
    assert [event[1] for event in env.events] == ['configure']
    assert not state_path(env.root, 'synthetic-notes.json').exists()
    failed = runner.invoke(app, ['rem', '--root', str(env.root), 'sources', 'add', 'summaries', '--since', '30d'])
    assert failed.exit_code != 0 and '--since' in failed.output
    result = runner.invoke(app, ['rem', '--root', str(env.root), 'sources', 'connect', 'summaries',
                                 '--config', '/synthetic/selection.json'])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ['rem', '--root', str(env.root), 'sources', 'remove', 'notes'])
    assert result.exit_code == 0 and not hooks.selected(env.root).get('notes')


def test_public_dry_run_is_metadata_only_and_never_advances_progress(shared_sources, monkeypatch):
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    env.events.clear()
    before = read_json(state_path(env.root, 'progress.json'), {})
    monkeypatch.setattr(env.modules['notes'], 'fetch', lambda *a: pytest.fail('dry run fetched'))
    monkeypatch.setattr(env.modules['notes'], 'collect', lambda *a: pytest.fail('dry run read bodies'))
    result = service.run_sync(env.root, source='notes', dry_run=True, all_pending=True, scheduled=True)
    assert result['sources']['notes'] == {'body_reads': False, 'count': 1}
    assert read_json(state_path(env.root, 'progress.json'), {}) == before
    assert env.events == [('notes', 'pending')]


def test_cli_project_removal_uses_registered_configuration(shared_sources, monkeypatch):
    from connectonion.cli.main import app
    env = shared_sources
    env.select('tasks')
    options_seen = []
    def configure(root, **options):
        options_seen.append(options)
        return {'kind': 'tasks', 'folders': [], 'enabled': False}
    monkeypatch.setattr(env.modules['tasks'], 'configure', configure)
    result = CliRunner().invoke(app, ['rem', '--root', str(env.root), 'sources',
                                    'remove', 'tasks', '--project', '200'])
    assert result.exit_code == 0, result.output
    assert options_seen == [{'remove': True, 'project': '200'}]
    assert not hooks.selected(env.root)


def test_public_sync_repeat_change_and_exact_citation(shared_sources):
    env = shared_sources
    env.select('summaries')
    seen = []
    def runner(book, items, config, kind=''):
        seen.extend(items)
        assert kind == 'summaries'
        return {'changed': [], 'usage': {'input_tokens': 10}}
    first = service.run_sync(env.root, source='summaries', runner=runner)
    assert first['outcome'] == 'completed' and first['items'] == 1
    old = seen[0]['source']
    again = service.run_sync(env.root, source='summaries', runner=runner)
    assert again['outcome'] == 'no_change' and len(seen) == 1
    env.current['summaries'] = 2
    changed = service.run_sync(env.root, source='summaries', runner=runner)
    assert changed['items'] == 1 and len(seen) == 2
    assert hooks.cited(env.root, old)['excerpt'] == 'Atlas saved version 1'


@pytest.mark.parametrize('target', [citation(kind) for kind in ('notes', 'tasks', 'summaries')]
                         + ['gmail:0123456789ab'])
def test_investigation_queue_recognizes_saved_source_citations(shared_sources, target):
    from connectonion.rem.files import Notebook
    from connectonion.rem.queue import hollow_investigations
    env = shared_sources
    notebook = Notebook(env.root)
    record = 'people/atlas.md'
    notebook.stub_person(record, 'Atlas', [])
    notebook.note_investigation(record, 'saved sources')
    assert record in hollow_investigations(env.root)
    notebook.write(record, notebook.read(record).replace('- (none yet)', f'- [1] {target}'))
    assert record not in hollow_investigations(env.root)
    assert env.loaded == []  # Citation recognition must not import a provider.


@pytest.mark.parametrize('old,new', [(citation(kind), citation(kind, 2))
                         for kind in ('notes', 'tasks', 'summaries')]
                         + [('gmail:0123456789ab', 'gmail:fedcba987654')])
def test_maintenance_skips_cited_material_but_keeps_new_versions(shared_sources, old, new):
    from connectonion.rem.files import Notebook
    from connectonion.rem.leads import nothing_new
    env = shared_sources
    notebook = Notebook(env.root)
    record = 'people/atlas.md'
    notebook.stub_person(record, 'Atlas', [])
    notebook.write(record, notebook.read(record).replace('- (none yet)', f'- [1] {old}'))
    assert nothing_new(notebook, record, [{'source': old, 'text': 'Atlas saved version 1'}])
    assert not nothing_new(notebook, record, [{'source': new, 'text': 'Atlas saved version 2'}])
    assert env.loaded == []


def test_failed_runner_preserves_source_checkpoint_for_retry(shared_sources):
    from connectonion.rem.runner import RunFailed
    env = shared_sources
    env.select('notes')
    before = read_json(state_path(env.root, 'progress.json'), {}).get('notes')
    def failed(*args, **kwargs):
        raise RunFailed('synthetic model failure')
    result = service.run_sync(env.root, source='notes', runner=failed)
    assert result['outcome'] == 'failed'
    assert read_json(state_path(env.root, 'progress.json'), {}).get('notes') == before
    assert hooks.collect(env.root, 'notes', before or {}, 5, 10000).items


def test_mail_only_sync_does_not_acquire_registered_sources(shared_sources, monkeypatch):
    env = shared_sources
    env.select('notes', 'tasks', 'summaries')
    monkeypatch.setattr(hooks, 'fetch', lambda *a, **kw: pytest.fail('mail-only sync fetched source'))
    result = service.run_sync(env.root, with_person='person@example.test', runner=lambda *a, **kw: pytest.fail('no mail'))
    assert result['items'] == 0
    assert all(event[1] not in ('fetch', 'collect') for event in env.events)


def test_public_gather_passes_window_and_owner_and_stays_offline(shared_sources, monkeypatch):
    from connectonion.rem.investigate import gather
    env = shared_sources
    env.select('tasks')
    hooks.fetch(env.root)
    monkeypatch.setattr(hooks, 'fetch', lambda *a, **kw: pytest.fail('investigation acquired material'))
    items, lines = gather('Atlas', ['Atlas'], days=1, clients={}, subscriptions=hooks.selected(env.root),
                          archive_root=env.root, record='people/atlas.md', sent_only=True)
    assert len(items) == 1
    calls = [event[2] for event in env.events if event[1] == 'gather']
    assert calls[0]['owner'] and calls[0]['start'] < calls[0]['end']
    service.toggle_source(env.root, 'tasks', False)
    _, lines = gather('Atlas', ['Atlas'], days=1, clients={}, subscriptions={},
                       archive_root=env.root, record='people/atlas.md')
    assert not any(line.startswith('tasks:') for line in lines)


def test_writer_waits_for_notebook_while_offline_reads_committed_snapshot(shared_sources, monkeypatch):
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    writer_lock, acquired, finished = Lock(), Event(), Event()
    failures = []
    def acquire(root, sub):
        with writer_lock:
            acquired.set()
            with hooks.acquisition_guard(root, sub)():
                pass  # Publication is serialized; the prior snapshot stays readable.
        return {'added': 0}
    monkeypatch.setattr(env.modules['notes'], 'fetch', acquire)
    def background():
        try:
            hooks.fetch(env.root)
        except Exception as error:
            failures.append(error)
        finally:
            finished.set()
    worker = Thread(target=background, daemon=True)
    with maintenance_lock(env.root):
        worker.start()
        assert acquired.wait(2)
        assert not finished.is_set()
        # The contract forbids this offline hook from waiting on writer_lock.
        assert hooks.collect(env.root, 'notes', {}, 2, 10000).items
    worker.join(2)
    assert finished.is_set() and not failures


def test_retry_revalidates_source_before_next_model_turn(shared_sources):
    from connectonion.rem import runner
    from connectonion.rem.config import read_config
    from connectonion.rem.inquiry import stage_config
    env = shared_sources
    env.select('summaries')
    hooks.fetch(env.root)
    items = hooks.collect(env.root, 'summaries', {}, 2, 10000).items
    calls = []
    def timeout(*args, **kwargs):
        calls.append('called')
        service.toggle_source(env.root, 'summaries', False)
        raise runner.RunFailed('timed out')
    retry = runner._retry_timeouts({'timeouts_retried': 0}, hooks.guard_turn(env.root, items, timeout))
    with pytest.raises(RemError, match='no longer approved'):
        retry(env.root, 'saved evidence', stage_config(env.root, read_config(env.root), 'enrich'), 'enrich')
    assert calls == ['called']


def test_collect_displays_source_receipt_and_backlog_and_keeps_collect_next(shared_sources, monkeypatch):
    from connectonion.cli.main import app
    from connectonion.rem import daily
    env = shared_sources
    env.select('notes')
    original = service.run_sync
    monkeypatch.setattr(service, 'run_sync', lambda root, **options: original(
        root, runner=lambda *a, **kw: {'changed': []}, **options))
    monkeypatch.setattr(daily, 'run_daily', lambda *a, **kw: pytest.fail('collect investigated'))
    command = ['rem', '--root', str(env.root), 'collect', '--source', 'notes']
    for expected in ('added: 1', 'unchanged: 1'):
        result = CliRunner().invoke(app, command, terminal_width=200)
        assert result.exit_code == 0, result.output
        assert 'Source collected' in result.output and expected in result.output
        assert 'Still waiting' in result.output
        assert result.output.rstrip().endswith(f'Next: co rem --root {env.root} collect --source notes')
    assert len([event for event in env.events if event[1] == 'fetch']) == 2


@pytest.mark.parametrize('driven', [False, True])
def test_pending_native_task_refuses_revoked_material_before_switching_worker(shared_sources, driven):
    from connectonion.rem import native
    env = shared_sources
    env.select('summaries')
    hooks.fetch(env.root)
    items = hooks.collect(env.root, 'summaries', {}, 2, 10000).items
    task = {'directory': str(state_path(env.root, 'tasks/revoked')),
            'task': {'items': items}, 'driven': not driven, 'run': {'model': 'old-worker'}}
    service.toggle_source(env.root, 'summaries', False)

    with pytest.raises(RemError, match='no longer approved'):
        native._offer_pending(env.root, task, driven=driven, takeover=True)
    assert task['driven'] is not driven and task['run'] == {'model': 'old-worker'}


def test_runner_check_blocks_revoked_prior_material_before_abstract_report(shared_sources, monkeypatch):
    from connectonion.rem import runner
    env = shared_sources
    env.select('summaries')
    hooks.fetch(env.root)
    items = hooks.collect(env.root, 'summaries', {}, 2, 10000).items
    service.toggle_source(env.root, 'summaries', False)
    monkeypatch.setattr(runner, '_collect_abstract_report',
                        lambda *a: pytest.fail('revoked material reached abstract report'))

    with pytest.raises(RemError, match='no longer approved'):
        runner.check({'root': str(env.root), 'items': [], 'prior_items': items}, {})


def test_native_source_fetch_has_a_deadline_without_holding_the_notebook_lock(shared_sources, monkeypatch):
    from contextlib import contextmanager
    from connectonion.rem import native
    env = shared_sources
    env.select('notes')
    watching = []
    @contextmanager
    def watch(root):
        watching.append('started')
        try:
            yield
        finally:
            watching.append('stopped')
    original = env.modules['notes'].fetch
    def fetch(root, sub):
        assert watching == ['started']
        assert native._WATCH['deadline'] > native.time.monotonic()
        assert native._WATCH['step'] == 'collecting selected sources'
        with maintenance_lock(root):
            pass  # The network phase must allow another notebook writer.
        return original(root, sub)
    monkeypatch.setattr(native, '_watching', watch)
    monkeypatch.setattr(native, '_stop', lambda *a: (None, {}))
    monkeypatch.setattr(env.modules['notes'], 'fetch', fetch)

    native._fetch_sources(env.root, scheduled=False, in_round=False)
    assert watching == ['started', 'stopped'] and native._WATCH['deadline'] is None
    assert hooks.collect(env.root, 'notes', {}, 2, 10000).items


def test_interrupted_source_fetch_unwinds_and_reports_a_preparation_stall(shared_sources, monkeypatch):
    import signal
    from connectonion.rem import native
    if not hasattr(signal, 'pthread_kill'):
        pytest.skip('Native preparation interruption requires POSIX thread signals')
    env = shared_sources
    env.select('notes')
    previous = signal.getsignal(signal.SIGUSR1)
    def interrupt(root, sub):
        assert native._WATCH['interrupt'] is not None
        write_json(state_path(root, native.STALLED), {
            'label': 'collecting selected sources', 'step': 'collecting selected sources'})
        raise native._Interrupted()  # Deliver the deadline signal's exception without waiting ten minutes.
    monkeypatch.setattr(native, '_stop', lambda *a: (None, {}))
    monkeypatch.setattr(env.modules['notes'], 'fetch', interrupt)

    with pytest.raises(native.PreparationStalled, match='collecting selected sources'):
        native._fetch_sources(env.root, scheduled=False, in_round=True)
    assert signal.getsignal(signal.SIGUSR1) == previous
    assert native._WATCH['interrupt'] is None and native._WATCH['deadline'] is None
    with maintenance_lock(env.root):
        pass
    assert not state_path(env.root, 'synthetic-notes.json').exists()


def _pending_source_extract(env, monkeypatch):
    from connectonion.rem import native, native_round
    env.select('notes')
    hooks.fetch(env.root)
    items = hooks.collect(env.root, 'notes', {}, 2, 10000).items
    task_id = 'native-' + 'a' * 32
    directory = state_path(env.root, f'tasks/{task_id}')
    write_json(directory / 'task.json', {
        'id': task_id, 'status': 'pending', 'directory': str(directory), 'handler': 'extract',
        'task': {'items': items}, 'inputs': {}, 'source_view': None})
    write_json(state_path(env.root, 'round.json'), {'pending': task_id})
    monkeypatch.setattr(native_round, 'recover_commit', lambda *a: None)
    monkeypatch.setattr(native, '_promoted', lambda *a: False)
    monkeypatch.setattr(native, '_inputs', lambda *a, **kw: {})
    monkeypatch.setattr(native, '_check_submission', lambda *a: pytest.fail('invalid source reached promotion'))
    return task_id


def test_submit_classifies_revoked_source_as_a_task_fault(shared_sources, monkeypatch):
    from connectonion.rem import native
    env = shared_sources
    task_id = _pending_source_extract(env, monkeypatch)
    service.toggle_source(env.root, 'notes', False)

    with pytest.raises(native.TaskFault, match='no longer approved'):
        native._submit(env.root, task_id, usage=None)


def test_submit_does_not_hide_notebook_io_errors_as_a_task_fault(shared_sources, monkeypatch):
    from connectonion.rem import native
    env = shared_sources
    task_id = _pending_source_extract(env, monkeypatch)
    def unreadable(*args):
        raise RemError('Unreadable source ownership file')
    monkeypatch.setattr(hooks, 'material_approved', unreadable)

    with pytest.raises(RemError, match='Unreadable source ownership file') as error:
        native._submit(env.root, task_id, usage=None)
    assert not isinstance(error.value, native.TaskFault)


@pytest.mark.parametrize('cursor,night,discard,collect_only,expected', [
    ({'done': False, 'catchup_night': 1}, 1, False, False, False),
    ({'done': False, 'catchup_night': 1}, 2, False, False, True),
    ({'done': False, 'catchup_night': 1, 'pending': 'open'}, 2, False, False, False),
    ({'done': False, 'catchup_night': 1, 'pending': 'open'}, 1, True, False, True),
    ({'done': True}, None, False, True, True),
    ({'done': False}, None, False, True, False),
])
def test_native_acquires_for_fresh_rounds_but_not_pending_work(
        shared_sources, monkeypatch, cursor, night, discard, collect_only, expected):
    from connectonion.rem import catchup, native
    env = shared_sources
    env.select('notes')
    write_json(state_path(env.root, 'round.json'), cursor)
    monkeypatch.setattr(catchup, 'number', lambda root: night)
    monkeypatch.setattr(native, '_stop', lambda *a: ('model held' if collect_only else None, {}))

    native._fetch_sources(env.root, scheduled=False, in_round=False,
                          discard=discard, collect_only=collect_only)
    assert any(event[1] == 'fetch' for event in env.events) is expected


def test_repeated_source_stalls_hold_before_another_acquisition(shared_sources, monkeypatch):
    from connectonion.rem import native
    env = shared_sources
    env.select('notes')
    write_json(state_path(env.root, 'round.json'), {
        'done': True, 'unnamed_stalls': native.STALL_HOLD_AFTER,
        'unnamed_stall_step': 'collecting selected sources',
        'unnamed_stall_at': service.now().isoformat()})
    monkeypatch.setattr(hooks, 'fetch', lambda *a, **kw: pytest.fail('held source fetched again'))

    native._fetch_sources(env.root, scheduled=False, in_round=False)
    assert 'collecting selected sources' in read_json(state_path(env.root, 'round-held.json'), {})['reason']


@pytest.mark.parametrize('kind', ['notes', 'tasks', 'summaries'])
@pytest.mark.parametrize('format', ['topics', 'pages', 'legacy'])
def test_topic_scan_preserves_registered_and_opaque_citations(shared_sources, kind, format):
    from connectonion.rem.files import Notebook
    from connectonion.rem.topic_map import scan_topics
    from tests.unit.test_rem_topic_map import topic
    env = shared_sources
    book = Notebook(env.root)
    targets = [citation(kind, account=f'account{i}') for i in range(3)]
    if format == 'pages':
        book.write('people/mara.md', '# Mara\n## Insight\n- **Thermal storage** stores heat. [1][2]\n'
                   f'## Sources\n- [1] {targets[0]} — 2026-01-01\n- [2] {targets[1]} — 2026-01-08\n')
        book.write('projects/cove.md', '# Cove\n- Thermal storage for the port. [1]\n'
                   f'## Sources\n- [1] {targets[2]} — 2026-01-15\n')
    elif format == 'topics':
        path = topic(book)
        text = path.read_text(encoding='utf-8')
        for index, target in enumerate(targets):
            text = text.replace(f'gmail:source{index}', target)
        path.write_text(text, encoding='utf-8')
    else:
        book.write('people/mara.md', '# Mara\n## Sources\n'
                   f'- [1] {targets[0]}\n- [2] {targets[1]}\n')
        book.write('projects/cove.md', f'# Cove\n## Sources\n- [1] {targets[2]}\n')
        days = ['2026-01-01', '2026-01-08', '2026-01-15']
        lines = [f'- **Thermal storage** stores heat — Mara, {day}, {target}'
                 for day, target in zip(days, targets)]
        path = state_path(env.root, 'extracts/legacy.md')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('## Knowledge\n' + '\n'.join(lines), encoding='utf-8')

    row, = scan_topics(book)
    assert row['qualified'] and row['source_count'] == 3
    assert {entry['source'] for entry in row['evidence']} == set(targets)
    assert env.loaded == []
