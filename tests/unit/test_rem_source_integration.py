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
        retry(env.root, 'saved evidence', {'runner': 'codex'}, 'enrich')
    assert calls == ['called']
