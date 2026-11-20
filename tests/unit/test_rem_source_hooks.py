"""Shared lifecycle contract using three synthetic saved-source representations."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Event, Thread, current_thread

import pytest

from connectonion.rem import service, source_hooks as hooks, source_versions
from connectonion.rem.files import RemError, maintenance_lock, read_json, state_path, write_json
from connectonion.rem.source import Batch
from tests.unit.rem_source_fixtures import citation, shared_sources


def gather(env, **options):
    return hooks.gather(env.root, ['Atlas'], start=datetime.now(timezone.utc) - timedelta(days=1),
                        record='projects/atlas.md', **options)


def test_no_selection_causes_no_provider_imports_or_coverage(shared_sources):
    env = shared_sources
    assert hooks.statuses(env.root) == hooks.consent_lines(env.root) == hooks.fetch(env.root) == {}
    assert gather(env) == ([], [])
    assert hooks.cited(env.root, citation('notes')) is None
    assert env.loaded == env.events == []


@pytest.mark.parametrize('state', ['unconfigured', 'disabled', 'unconsented', 'revoked-receipt'])
def test_inactive_states_never_import_providers(shared_sources, state):
    env = shared_sources
    if state != 'unconfigured':
        env.select('notes', approve=state != 'unconsented')
        if state == 'disabled':
            service.toggle_source(env.root, 'notes', False)
        if state == 'revoked-receipt':
            write_json(state_path(env.root, 'consent.json'), {})
    env.loaded.clear()
    env.events.clear()
    hooks.statuses(env.root)
    hooks.consent_lines(env.root)
    service.consent_summary(env.root)
    assert hooks.fetch(env.root) == {}
    assert gather(env) == ([], [])
    assert hooks.cited(env.root, citation('notes')) is None
    if state != 'unconfigured' and state != 'disabled':
        assert hooks.pending(env.root, 'notes', {})['consented'] is False
    with pytest.raises(RemError, match='authorized'):
        hooks.collect(env.root, 'notes', {}, 5, 10000)
    assert env.loaded == env.events == []


def test_configure_is_explicit_exception_and_consent_scope_is_stable(shared_sources):
    env = shared_sources
    env.select('summaries', approve=False)
    before = service.consent_summary(env.root)
    assert before['sources']['summaries']['scope']['folders'] == ['Work']
    service.approve_sources(env.root)
    assert before == service.consent_summary(env.root)
    assert env.loaded == []
    assert hooks.approved(env.root, 'summaries')


def test_configure_rejects_unsupported_options_without_acquisition(shared_sources):
    env = shared_sources
    with pytest.raises(RemError, match='--since'):
        hooks.configure(env.root, 'summaries', since='30d')
    assert not hooks.selected(env.root)
    assert all(event[1] == 'configure' for event in env.events)


def test_slow_configuration_cannot_undo_concurrent_removal(shared_sources, monkeypatch):
    env = shared_sources
    env.select('notes')
    before = hooks.selected(env.root)['notes']
    def configure(root, **options):
        service.toggle_source(root, 'notes', False)
        return before
    monkeypatch.setattr(env.modules['notes'], 'configure', configure)
    with pytest.raises(RemError, match='configuration changed'):
        hooks.configure(env.root, 'notes')
    assert not hooks.selected(env.root)


def test_configuration_can_disable_an_empty_source_scope(shared_sources, monkeypatch):
    env = shared_sources
    env.select('tasks')
    monkeypatch.setattr(env.modules['tasks'], 'configure',
                        lambda *a, **kw: {'kind': 'tasks', 'folders': [], 'enabled': False})
    result = hooks.configure(env.root, 'tasks', remove=True, project='last-project')
    assert result['enabled'] is False
    saved = read_json(state_path(env.root, 'subscriptions.json'), {})['tasks']
    assert saved['unsubscribed'] and not saved['consented']
    assert not hooks.selected(env.root)


def test_configuration_rejects_non_boolean_enabled(shared_sources, monkeypatch):
    env = shared_sources
    monkeypatch.setattr(env.modules['tasks'], 'configure',
                        lambda *a, **kw: {'kind': 'tasks', 'enabled': 'false'})
    with pytest.raises(RemError, match='boolean'):
        hooks.configure(env.root, 'tasks')
    assert not hooks.selected(env.root)


@pytest.mark.parametrize('flag', ['enabled', 'consented', 'unsubscribed'])
def test_bad_boolean_flags_fail_before_import(shared_sources, flag):
    env = shared_sources
    env.select('notes')
    saved = read_json(state_path(env.root, 'subscriptions.json'), {})
    saved['notes'][flag] = 'false'
    write_json(state_path(env.root, 'subscriptions.json'), saved)
    with pytest.raises(RemError, match='flag'):
        hooks.fetch(env.root)
    assert env.loaded == []


def test_subscription_cannot_choose_module(shared_sources):
    env = shared_sources
    write_json(state_path(env.root, 'subscriptions.json'), {'x': {'kind': 'arbitrary.module', 'enabled': True}})
    assert hooks.fetch(env.root) == hooks.statuses(env.root) == {}
    assert env.loaded == []


@pytest.mark.parametrize('kind', ['notes', 'tasks', 'summaries'])
def test_collection_does_not_mutate_or_persist_caller_progress(shared_sources, kind):
    env = shared_sources
    env.select(kind)
    hooks.fetch(env.root)
    progress = {'nested': {'unchanged': [1]}}
    before = deepcopy(progress)
    batch = hooks.collect(env.root, kind, progress, 5, 10000)
    assert progress == before and batch.progress['last'] == citation(kind)
    assert read_json(state_path(env.root, 'progress.json'), {}) == {}
    assert hooks.collect(env.root, kind, batch.progress, 5, 10000).items == []


@pytest.mark.parametrize('kind', ['notes', 'tasks', 'summaries'])
def test_old_and_new_versions_resolve_independently(shared_sources, kind):
    env = shared_sources
    env.select(kind)
    hooks.fetch(env.root)
    first = hooks.collect(env.root, kind, {}, 5, 10000)
    env.current[kind] = 2
    hooks.fetch(env.root)
    second = hooks.collect(env.root, kind, first.progress, 5, 10000)
    old, new = first.items[0]['source'], second.items[0]['source']
    assert hooks.cited(env.root, old)['excerpt'] == 'Atlas saved version 1'
    assert hooks.cited(env.root, new)['excerpt'] == 'Atlas saved version 2'
    assert hooks.cited(env.root, citation(kind, 99)) is None
    assert hooks.superseded(env.root, {old}, {new}) == {old}
    assert hooks.superseded(env.root, {new}, {old}) == {new}
    assert hooks.superseded(env.root, {old}, set()) == set()


def test_opaque_routes_survive_restart_and_do_not_probe_other_providers(shared_sources, monkeypatch):
    from connectonion.rem import source_citations
    env = shared_sources
    env.select('summaries', 'notes', 'tasks')
    hooks.fetch(env.root, names={'summaries'})
    target = hooks.collect(env.root, 'summaries', {}, 2, 10000).items[0]['source']
    route = source_citations.lookup(env.root, target)
    assert route == {'kind': 'summaries', 'record': 'summaries:account:note', 'subscription': 'summaries'}
    env.loaded.clear()
    # A newly constructed Path and lookup have no process-local routing cache.
    from pathlib import Path
    assert hooks.cited(Path(str(env.root)), target)['excerpt'] == 'Atlas saved version 1'
    assert set(env.loaded) == {'synthetic_rem_summaries'}
    service.toggle_source(env.root, 'summaries', False)
    env.loaded.clear()
    assert hooks.cited(env.root, target) is None
    assert source_citations.lookup(env.root, target) == route
    assert env.loaded == []


def test_opaque_target_without_mapping_does_not_fall_back(shared_sources, monkeypatch):
    env = shared_sources
    env.select('summaries')
    hooks.fetch(env.root)
    monkeypatch.setitem(source_versions.KINDS, 'adapter', source_versions.Kind(
        lambda target: 'wrong', lambda *args: pytest.fail('global fallback bypassed routing')))
    assert hooks.version_context(env.root, citation('summaries')) is None
    assert env.loaded == ['synthetic_rem_summaries']  # fetch only


def test_route_conflict_preserves_original_entry(shared_sources):
    from connectonion.rem.source_citations import lookup, remember
    env = shared_sources
    env.select('summaries')
    hooks.fetch(env.root)
    target = hooks.collect(env.root, 'summaries', {}, 2, 10000).items[0]['source']
    original = lookup(env.root, target)
    with pytest.raises(RemError, match='Conflicting owner'):
        remember(env.root, {target: {**original, 'subscription': 'foreign'}})
    assert lookup(env.root, target) == original


def test_scope_and_model_changes_revoke_retained_material(shared_sources, monkeypatch):
    from connectonion.rem import config
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    items = hooks.collect(env.root, 'notes', {}, 2, 10000).items
    previous = config.read_config
    monkeypatch.setattr(config, 'read_config', lambda *a, **kw: {**previous(*a, **kw), 'model': 'different'})
    assert not hooks.material_approved(env.root, items)
    monkeypatch.setattr(config, 'read_config', previous)
    hooks.configure(env.root, 'notes', folders=['Private'])
    assert not hooks.material_approved(env.root, items)
    service.approve_sources(env.root)
    assert not hooks.material_approved(env.root, items)


def test_failure_receipts_block_until_success_and_other_sources_continue(shared_sources):
    env = shared_sources
    env.select('notes', 'tasks')
    hooks.fetch(env.root)
    env.failures['notes'] = hooks.SourceUnavailable('account mismatch', allow_saved=False)
    failed = hooks.fetch(env.root)
    assert failed['notes']['allow_saved'] is False and failed['tasks']['ok']
    assert hooks.cited(env.root, citation('notes')) is None
    env.failures['notes'] = hooks.SourceUnavailable('temporary unavailable')
    assert hooks.fetch(env.root)['notes']['allow_saved'] is False
    with pytest.raises(hooks.SourceUnavailable):
        hooks.collect(env.root, 'notes', {}, 2, 10000)
    del env.failures['notes']
    assert hooks.fetch(env.root)['notes']['ok']
    assert hooks.cited(env.root, citation('notes')) is not None


def test_temporary_failure_explains_stale_material(shared_sources):
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    env.failures['notes'] = hooks.SourceUnavailable('temporary unavailable')
    hooks.fetch(env.root)
    items, lines = gather(env)
    assert items and any('may be stale' in line for line in lines)


@pytest.mark.parametrize('order', ['success-before-block', 'retry-before-new-block', 'failure-after-success'])
def test_overlapping_acquisition_cannot_clear_a_block_without_a_fresh_retry(shared_sources, monkeypatch, order):
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    if order == 'retry-before-new-block':
        env.failures['notes'] = hooks.SourceUnavailable('account mismatch', allow_saved=False)
        hooks.fetch(env.root)
        del env.failures['notes']
    original = env.modules['notes'].fetch
    paused, resume = Event(), Event()
    results, errors = [], []

    def fetch(root, sub):
        if current_thread() is worker:
            result = original(root, sub)
            paused.set()
            assert resume.wait(5), 'foreground did not release the overlapping fetch'
            if order == 'failure-after-success':
                raise hooks.SourceUnavailable('account mismatch', allow_saved=False)
            return result
        if order != 'failure-after-success':
            raise hooks.SourceUnavailable('account mismatch', allow_saved=False)
        return original(root, sub)

    def background():
        try:
            results.append(hooks.fetch(env.root))
        except Exception as error:
            errors.append(error)

    monkeypatch.setattr(env.modules['notes'], 'fetch', fetch)
    worker = Thread(target=background, daemon=True)
    worker.start()
    try:
        assert paused.wait(5), 'background fetch did not reach publication boundary'
        foreground = hooks.fetch(env.root)
        assert foreground['notes']['ok'] is (order == 'failure-after-success')
    finally:
        resume.set()
        worker.join(5)
    assert not worker.is_alive() and not errors
    assert results[0]['notes']['ok'] is False and results[0]['notes']['allow_saved'] is False
    assert hooks.cited(env.root, citation('notes')) is None
    with pytest.raises(hooks.SourceUnavailable):
        hooks.collect(env.root, 'notes', {}, 2, 10000)
    assert gather(env)[0] == []
    monkeypatch.setattr(env.modules['notes'], 'fetch', original)
    assert hooks.fetch(env.root)['notes']['ok']
    assert hooks.cited(env.root, citation('notes')) is not None


def test_unexpected_fetch_errors_propagate(shared_sources):
    env = shared_sources
    env.select('notes')
    env.failures['notes'] = TypeError('programming defect')
    with pytest.raises(TypeError, match='programming defect'):
        hooks.fetch(env.root)


def test_fetch_runs_outside_lock_and_commit_guard_rechecks_revocation(shared_sources, monkeypatch):
    from connectonion.rem import files
    env = shared_sources
    env.select('notes')
    def fetch(root, sub):
        # A non-reentrant notebook lock can be taken during the network phase.
        with files.maintenance_lock(root):
            pass
        service.toggle_source(root, 'notes', False)
        with hooks.acquisition_guard(root, sub)():
            pytest.fail('revoked acquisition was allowed to publish')
    monkeypatch.setattr(env.modules['notes'], 'fetch', fetch)
    result = hooks.fetch(env.root)
    assert not result['notes']['ok'] and result['notes']['allow_saved'] is False
    assert not state_path(env.root, 'synthetic-notes.json').exists()


def test_offline_hooks_reuse_notebook_lock_only(shared_sources, monkeypatch):
    from connectonion.rem import files
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    original = files.maintenance_lock
    with original(env.root):
        monkeypatch.setattr(files, 'maintenance_lock', lambda *a, **kw: pytest.fail('recursive lock'))
        assert hooks.collect(env.root, 'notes', {}, 2, 10000).items
    monkeypatch.setattr(files, 'maintenance_lock', original)
    with original(env.root):
        with pytest.raises(RemError):
            with original(env.root):
                pytest.fail('ordinary lock became reentrant')


@pytest.mark.parametrize('blocked', [False, True])
def test_busy_publication_records_failure_and_continues_other_sources(shared_sources, monkeypatch, blocked):
    from concurrent.futures import ThreadPoolExecutor
    from connectonion.rem import files
    env = shared_sources
    env.select('notes', 'tasks')
    hooks.fetch(env.root)
    if blocked:
        env.failures['notes'] = hooks.SourceUnavailable('account refused', allow_saved=False)
        hooks.fetch(env.root, names={'notes'})
        del env.failures['notes']
    env.events.clear()
    # Keep this contention test short even against the old implementation.
    monkeypatch.setattr(files, 'WRITE_WAIT_SECONDS', 0.02)
    monkeypatch.setattr(hooks, 'ACQUISITION_WAIT_SECONDS', 0.02, raising=False)
    holding, release = Event(), Event()
    def maintain():
        with maintenance_lock(env.root):
            holding.set()
            assert release.wait(5), 'fetch waited on the long notebook transaction'
    with ThreadPoolExecutor(max_workers=1) as pool:
        holder = pool.submit(maintain)
        try:
            assert holding.wait(2)
            results = hooks.fetch(env.root)
            assert results['notes']['ok'] is results['tasks']['ok'] is False
            assert results['notes']['allow_saved'] is (not blocked)
            assert results['tasks']['allow_saved'] is True
            assert {event[0] for event in env.events if event[1] == 'fetch'} == {'notes', 'tasks'}
            saved = read_json(state_path(env.root, 'source-acquisition.json'), {})
            assert saved['notes']['allow_saved'] is (not blocked)
            assert saved['tasks']['allow_saved'] is True
        finally:
            release.set()
        holder.result(timeout=2)
    assert (hooks.cited(env.root, citation('notes')) is None) is blocked


def test_publication_body_busy_error_is_not_reclassified(shared_sources):
    from connectonion.rem.files import MAINTENANCE_BUSY
    env = shared_sources
    env.select('notes')
    sub = hooks.selected(env.root)['notes']
    error = RemError(MAINTENANCE_BUSY)
    with pytest.raises(RemError) as caught:
        with hooks.acquisition_guard(env.root, sub)():
            raise error
    assert caught.value is error


def test_blocking_receipt_is_visible_to_next_turn_inside_notebook_lock(shared_sources):
    from concurrent.futures import ThreadPoolExecutor
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    items = hooks.collect(env.root, 'notes', {}, 1, 10000).items
    before = read_json(state_path(env.root, 'source-acquisition.json'), {})['notes']
    sub = hooks.selected(env.root)['notes']
    with ThreadPoolExecutor(max_workers=1) as pool:
        with maintenance_lock(env.root):
            assert hooks.guard_turn(env.root, items, lambda: 'first request')() == 'first request'
            future = pool.submit(hooks._record_acquisition, env.root, 'notes', sub, before,
                                 {'ok': False, 'allow_saved': False, 'error': 'account refused'})
            assert future.result(timeout=2)['allow_saved'] is False
            with pytest.raises(hooks.SourceMaterialUnavailable):
                hooks.guard_turn(env.root, items, lambda: pytest.fail('sent after block'))()


def test_concurrent_source_receipts_preserve_both_results(shared_sources):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    env = shared_sources
    env.select('notes', 'tasks')
    barrier = Barrier(2)
    def record(name):
        sub = hooks.selected(env.root)[name]
        barrier.wait(timeout=2)
        return hooks._record_acquisition(env.root, name, sub, {},
                                         {'ok': False, 'allow_saved': False, 'error': name})
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(not result['ok'] for result in pool.map(record, ('notes', 'tasks')))
    saved = read_json(state_path(env.root, 'source-acquisition.json'), {})
    assert saved['notes']['error'] == 'notes'
    assert saved['tasks']['error'] == 'tasks'


def test_strict_budgets_and_first_item_clipping(shared_sources):
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    item = hooks.collect(env.root, 'notes', {}, 1, 10000).items[0]
    large = {**item, 'text': 'x' * 5000}
    fitted, limited = hooks.bounded([large, item], 2, 1000)
    assert limited and len(fitted) == 1 and hooks.material_size(fitted) <= 1000
    assert '[truncated by co rem:' in fitted[0]['text']
    assert fitted[0]['source'] == item['source']
    with pytest.raises(hooks.SourceBudgetExceeded):
        hooks.bounded([large], 1, 10)


def test_adapter_cannot_commit_over_budget_result(shared_sources, monkeypatch):
    env = shared_sources
    env.select('notes')
    monkeypatch.setattr(env.modules['notes'], 'collect', lambda *args: Batch([{'text': 'x' * 10000}], {'last': 'bad'}))
    with pytest.raises(RemError, match='exceeded the batch budget'):
        hooks.collect(env.root, 'notes', {}, 1, 100)
    assert not state_path(env.root, 'source-citations.json').exists()
    assert not state_path(env.root, 'progress.json').exists()


def test_gather_passes_owner_end_and_aggregate_budget(shared_sources):
    env = shared_sources
    env.select('notes', 'tasks', 'summaries')
    hooks.fetch(env.root)
    end = datetime.now(timezone.utc) + timedelta(seconds=1)
    items, lines = gather(env, end=end, owner=True, max_items=1, max_chars=10000)
    assert len(items) == 1 and hooks.material_size(items) <= 10000
    calls = [event for event in env.events if event[1] == 'gather']
    assert len(calls) == 1 and calls[0][2]['owner'] is True and calls[0][2]['end'] == end
    assert sum('budget exhausted' in line for line in lines) == 2


@pytest.mark.parametrize('limits', [(0, 10), (1, 0), (True, 100), (1, False)])
def test_invalid_limits_fail_before_import(shared_sources, limits):
    env = shared_sources
    env.select('notes')
    with pytest.raises(ValueError):
        hooks.collect(env.root, 'notes', {}, *limits)
    assert env.loaded == []


def test_naive_or_reversed_gather_window_fails(shared_sources):
    env = shared_sources
    env.select('notes')
    with pytest.raises(ValueError, match='time window'):
        hooks.gather(env.root, ['Atlas'], start=datetime.now(), record='projects/atlas.md')
    with pytest.raises(ValueError, match='time window'):
        gather(env, end=datetime(2000, 1, 1, tzinfo=timezone.utc))
    assert env.loaded == []


def test_retained_native_and_followup_material_rechecks_current_scope(shared_sources):
    env = shared_sources
    env.select('summaries')
    hooks.fetch(env.root)
    items = hooks.collect(env.root, 'summaries', {}, 2, 10000).items
    directory = state_path(env.root, 'tasks/example')
    write_json(directory / 'material.json', [])
    write_json(directory / 'original.json', items)
    task = {'directory': str(directory), 'task': {'items': [], 'prior_items': items}}
    calls = []
    execute = hooks.guard_turn(env.root, items, lambda: calls.append('model'))
    execute()
    hooks.task_material(env.root, task)
    service.toggle_source(env.root, 'summaries', False)
    with pytest.raises(RemError, match='no longer approved'):
        execute()
    with pytest.raises(RemError, match='no longer approved'):
        hooks.task_material(env.root, task)
    with pytest.raises(RemError, match='no longer approved'):
        hooks.require_material(env.root, [{'role': 'original_evidence', 'file': str(directory / 'original.json')}])
    assert calls == ['model']
