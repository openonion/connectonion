"""Selected-source integration with a synthetic vault, no model or real home."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.rem import obsidian, obsidian_source, obsidian_store, service, source_hooks
from connectonion.rem.config import prepare, read_config
from connectonion.rem.files import Notebook, RemError, maintenance_lock, read_json, state_path, write_json


@pytest.fixture
def selected(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'mail_available', lambda kind: False)
    monkeypatch.setattr(service, 'codex_sessions_root', lambda: tmp_path / 'absent-codex')
    monkeypatch.setattr(service, 'claude_projects_root', lambda: tmp_path / 'absent-claude')
    root, vault = tmp_path / 'notebook', tmp_path / 'Vault'
    prepare(root)
    for name in ("codex", "claude-code", "gmail", "outlook", "whatsapp"):
        service.toggle_source(root, name, False)
    (vault / 'Work').mkdir(parents=True)
    (vault / 'Private').mkdir()
    (vault / 'Work' / 'Atlas.md').write_text('Atlas first version', encoding='utf-8')
    (vault / 'Private' / 'Diagnosis.md').write_text('private sibling', encoding='utf-8')
    obsidian.save_selection(root, vault, ['Work'])
    return root.resolve(), vault.resolve()


def approve(root):
    service.approve_sources(root)


def test_registration_and_declined_consent_never_read_note_bodies(selected, monkeypatch):
    root, _ = selected
    monkeypatch.setattr(obsidian, 'list_notes', lambda *a: pytest.fail('read before approval'))
    summary = service.consent_summary(root)
    assert summary['sources']['obsidian']['scope']['folders'] == ['Work']
    assert not service.ensure_consent(root, confirm=lambda value: False)
    assert source_hooks.fetch(root) == {}
    dry = service.run_sync(root, source='obsidian', dry_run=True)
    assert dry['sources']['obsidian']['body_reads'] is False
    assert not state_path(root, obsidian_store.DATABASE).exists()


def test_approved_fetch_offline_collect_and_citation_under_notebook_lock(selected, monkeypatch):
    root, vault = selected
    approve(root)
    assert source_hooks.fetch(root)['obsidian']['result']['added'] == 1
    monkeypatch.setattr(obsidian, 'list_notes', lambda *a: pytest.fail('offline read touched vault'))
    with maintenance_lock(root):
        batch = source_hooks.collect(root, 'obsidian', {}, 10, 10000)
        assert len(batch.items) == 1
        version = batch.items[0]['source']
        assert source_hooks.cited(root, version)['excerpt'] == 'Atlas first version'
    assert read_json(state_path(root, 'progress.json'), {}) == {}


def test_scope_change_requires_approval_again(selected):
    root, vault = selected
    approve(root)
    source_hooks.fetch(root)
    batch = source_hooks.collect(root, 'obsidian', {}, 10, 10000)
    obsidian.save_selection(root, vault, ['Private'])
    assert not source_hooks.material_approved(root, batch.items)
    assert source_hooks.cited(root, batch.items[0]['source']) is None
    approve(root)
    assert not source_hooks.material_approved(root, batch.items)


def test_exact_old_version_and_same_record_replacement(selected):
    from connectonion.rem import page_review, reader_model
    root, vault = selected
    approve(root)
    source_hooks.fetch(root)
    old = source_hooks.collect(root, 'obsidian', {}, 10, 10000)
    (vault / 'Work' / 'Atlas.md').write_text('Atlas second version', encoding='utf-8')
    source_hooks.fetch(root)
    new = source_hooks.collect(root, 'obsidian', old.progress, 10, 10000)
    before, after = old.items[0]['source'], new.items[0]['source']
    assert before != after
    assert source_hooks.cited(root, before)['excerpt'] == 'Atlas first version'
    assert source_hooks.superseded(root, {before}, {after}) == {before}
    assert page_review._lost_sources('\n## Sources\n- [1] ' + before,
                                     '\n## Sources\n- [1] ' + after, root=root) == set()


def test_unselected_source_adds_no_import_or_coverage(tmp_path, monkeypatch):
    original = source_hooks.importlib.import_module
    def load(name):
        if name == 'connectonion.rem.obsidian_source':
            pytest.fail('unselected source imported')
        return original(name)
    monkeypatch.setattr(source_hooks.importlib, 'import_module', load)
    assert source_hooks.statuses(tmp_path) == {}
    assert source_hooks.gather(tmp_path, ['Atlas'], start=datetime(2000, 1, 1, tzinfo=timezone.utc),
                               record='projects/atlas.md') == ([], [])


def test_dry_run_uses_only_saved_index_and_respects_committed_progress(selected, monkeypatch):
    root, _ = selected
    approve(root)
    source_hooks.fetch(root)
    monkeypatch.setattr(obsidian_store, '_decode', lambda *a: pytest.fail('dry-run decoded body'))
    assert service.run_sync(root, source='obsidian', dry_run=True)['sources']['obsidian']['pending_notes'] == 1


def test_removal_revokes_material_and_preserves_original_vault(selected):
    root, vault = selected
    approve(root)
    source_hooks.fetch(root)
    batch = source_hooks.collect(root, 'obsidian', {}, 10, 10000)
    service.toggle_source(root, 'obsidian', False)
    assert not source_hooks.material_approved(root, batch.items)
    assert source_hooks.cited(root, batch.items[0]['source']) is None
    assert (vault / 'Work' / 'Atlas.md').read_text() == 'Atlas first version'


def test_public_sync_first_repeat_and_incremental_preserve_exact_citations(selected):
    root, vault = selected
    approve(root)
    seen = []
    def runner(notebook, items, config, kind=''):
        seen.extend(item for item in items if item.get('source', '').startswith('obsidian:'))
        return {'usage': {'input_tokens': 10}, 'changed': []}
    first = service.run_sync(root, source='obsidian', runner=runner)
    assert first['outcome'] == 'completed' and first['items'] == 1
    assert first['acquisition']['obsidian']['result']['added'] == 1
    before = read_json(state_path(root, 'progress.json'), {})
    again = service.run_sync(root, source='obsidian', runner=runner)
    assert again['outcome'] == 'no_change' and again['items'] == 0
    assert len(seen) == 1
    (vault / 'Work' / 'Atlas.md').write_text('Atlas revised deadline', encoding='utf-8')
    changed = service.run_sync(root, source='obsidian', runner=runner)
    assert changed['items'] == 1
    assert seen[0]['source'] != seen[1]['source']
    from connectonion.rem.reader_model import cited_context
    page = '\n## Sources\n- [1] ' + seen[0]['source'] + '\n'
    context = cited_context(root, [{'text': page}])
    assert context[seen[0]['source']]['excerpt'] == 'Atlas first version'
    assert read_json(state_path(root, 'progress.json'), {}) != before


def test_failed_model_keeps_source_progress_for_retry(selected):
    from connectonion.rem.runner import RunFailed
    root, _ = selected
    approve(root)
    def failed(*args, **kwargs):
        raise RunFailed('synthetic model failure')
    before = read_json(state_path(root, 'progress.json'), {}).get('obsidian')
    result = service.run_sync(root, source='obsidian', runner=failed)
    assert result['outcome'] == 'failed'
    assert read_json(state_path(root, 'progress.json'), {}).get('obsidian') == before
    assert source_hooks.collect(root, 'obsidian', before or {}, 10, 10000).items


def test_cli_add_and_remove_do_not_collect_or_edit_vault(selected):
    from connectonion.cli.main import app
    root, vault = selected
    runner = CliRunner()
    result = runner.invoke(app, ['rem', '--root', str(root), 'sources', 'add', 'obsidian',
                                 '--vault', str(vault), '--folder', 'Work'])
    assert result.exit_code == 0, result.output
    assert 'start' in result.output
    assert not state_path(root, obsidian_store.DATABASE).exists()
    result = runner.invoke(app, ['rem', '--root', str(root), 'sources', 'remove', 'obsidian'])
    assert result.exit_code == 0, result.output
    assert (vault / 'Work' / 'Atlas.md').read_text() == 'Atlas first version'


def test_public_investigation_reads_only_saved_selected_notes(selected, monkeypatch):
    from connectonion.rem.investigate import gather
    root, _ = selected
    approve(root)
    source_hooks.fetch(root)
    monkeypatch.setattr(obsidian, 'list_notes', lambda *a: pytest.fail('investigation rescanned vault'))
    items, lines = gather('Atlas', ['Atlas'], days=365, clients={},
                          subscriptions={'obsidian': service.subscriptions(root)['obsidian']},
                          archive_root=root, record='projects/atlas.md')
    notes = [item for item in items if item.get('source', '').startswith('obsidian:')]
    assert len(notes) == 1 and notes[0]['text'] == 'Atlas first version'
    assert any('obsidian:' in line for line in lines)
    service.toggle_source(root, 'obsidian', False)
    items, lines = gather('Atlas', ['Atlas'], days=365, clients={}, subscriptions={},
                          archive_root=root, record='projects/atlas.md')
    assert not any('obsidian' in line for line in lines)


def test_native_replay_checks_prior_parts_and_original_evidence(selected):
    root, _ = selected
    approve(root)
    source_hooks.fetch(root)
    items = source_hooks.collect(root, 'obsidian', {}, 10, 10000).items
    directory = state_path(root, 'tasks/example')
    directory.mkdir(parents=True)
    write_json(directory / 'material.json', [])
    write_json(directory / 'original.json', items)
    task = {'directory': str(directory), 'task': {'items': [], 'prior_items': items}}
    source_hooks.task_material(root, task)
    service.toggle_source(root, 'obsidian', False)
    with pytest.raises(RemError, match='no longer approved'):
        source_hooks.task_material(root, task)
    with pytest.raises(RemError, match='no longer approved'):
        source_hooks.require_material(root, [{'role': 'original_evidence', 'file': str(directory / 'original.json')}])


def test_each_followup_turn_rechecks_current_approval(selected):
    root, _ = selected
    approve(root)
    source_hooks.fetch(root)
    items = source_hooks.collect(root, 'obsidian', {}, 10, 10000).items
    calls = []
    execute = source_hooks.guard_turn(root, items, lambda: calls.append('model'))
    execute()
    service.toggle_source(root, 'obsidian', False)
    with pytest.raises(RemError, match='no longer approved'):
        execute()
    assert calls == ['model']


def test_boolean_flag_without_matching_receipt_does_not_grant_access(selected):
    root, _ = selected
    sources = read_json(state_path(root, 'subscriptions.json'), {})
    sources['obsidian']['consented'] = True
    write_json(state_path(root, 'subscriptions.json'), sources)
    assert source_hooks.fetch(root) == {}
    with pytest.raises(RemError, match='not yet authorized'):
        source_hooks.collect(root, 'obsidian', {}, 10, 10000)


def test_source_content_reads_reuse_only_owned_notebook_lock(selected, monkeypatch):
    from connectonion.rem import files
    root, _ = selected
    approve(root)
    source_hooks.fetch(root)
    original = files.maintenance_lock
    with original(root):
        def forbidden(*args, **kwargs):
            pytest.fail('attempted to reacquire the owned notebook lock')
        monkeypatch.setattr(files, 'maintenance_lock', forbidden)
        assert source_hooks.collect(root, 'obsidian', {}, 10, 10000).items
    monkeypatch.setattr(files, 'maintenance_lock', original)
    with original(root):
        with pytest.raises(RemError):
            with original(root):
                pytest.fail('ordinary maintenance lock became reentrant')


def test_model_change_invalidates_saved_material(selected, monkeypatch):
    from connectonion.rem import config
    root, _ = selected
    approve(root)
    source_hooks.fetch(root)
    items = source_hooks.collect(root, 'obsidian', {}, 10, 10000).items
    original = config.read_config
    monkeypatch.setattr(config, 'read_config', lambda *a, **kw: {**original(*a, **kw), 'model': 'different-model'})
    assert not source_hooks.material_approved(root, items)
    assert source_hooks.fetch(root) == {}


def test_timeout_retry_checks_revocation_before_resending(selected):
    from connectonion.rem import runner
    root, _ = selected
    approve(root)
    source_hooks.fetch(root)
    items = source_hooks.collect(root, 'obsidian', {}, 10, 10000).items
    calls = []
    def timeout(*args, **kwargs):
        calls.append('model')
        service.toggle_source(root, 'obsidian', False)
        raise runner.RunFailed('timed out')
    retry = runner._retry_timeouts({'timeouts_retried': 0}, source_hooks.guard_turn(root, items, timeout))
    with pytest.raises(RemError, match='no longer approved'):
        retry(root, 'read retained material', {'runner': 'codex'}, 'enrich')
    assert calls == ['model']


def test_receipt_is_rechecked_after_waiting_for_acquisition_lock(selected, monkeypatch):
    from contextlib import contextmanager
    root, _ = selected
    approve(root)
    real_lock = obsidian_store.maintenance_lock
    @contextmanager
    def change_receipt_then_lock(root, **kwargs):
        receipt = read_json(state_path(root, 'consent.json'), {})
        receipt['summary_value']['model'] = 'different-model'
        write_json(state_path(root, 'consent.json'), receipt)
        with real_lock(root, **kwargs):
            yield
    monkeypatch.setattr(obsidian_store, 'maintenance_lock', change_receipt_then_lock)
    monkeypatch.setattr(obsidian, 'list_notes', lambda *a: pytest.fail('read after receipt changed'))
    with pytest.raises(obsidian_store.SnapshotUnavailable, match='receipt changed'):
        source_hooks.fetch(root)
    assert not state_path(root, obsidian_store.DATABASE).exists()
