"""Selected-source integration with a synthetic vault, no model or real home."""
from datetime import datetime, timezone
from pathlib import Path
import sys

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
    assert page_review._lost_sources({before}, {after}, root=root) == set()


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
        retry(root, 'read retained material', read_config(root), 'enrich')
    assert calls == ['model']


def test_receipt_is_rechecked_after_waiting_for_acquisition_lock(selected, monkeypatch):
    from contextlib import contextmanager
    root, _ = selected
    approve(root)
    real_lock = obsidian_store._file_lock
    @contextmanager
    def change_receipt_then_lock(path, wait, **kwargs):
        receipt = read_json(state_path(root, 'consent.json'), {})
        receipt['source_approvals']['obsidian']['execution']['model'] = 'different-model'
        write_json(state_path(root, 'consent.json'), receipt)
        with real_lock(path, wait, **kwargs):
            yield
    monkeypatch.setattr(obsidian_store, '_file_lock', change_receipt_then_lock)
    monkeypatch.setattr(obsidian, 'list_notes', lambda *a: pytest.fail('read after receipt changed'))
    result = source_hooks.fetch(root)['obsidian']
    assert result['ok'] is False
    assert result['allow_saved'] is False
    assert not state_path(root, obsidian_store.DATABASE).exists()


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks require privileges on Windows")
@pytest.mark.parametrize('redirect', ['folder', 'vault', 'ancestor', 'vault-loop', 'ancestor-loop'])
def test_redirected_scope_blocks_saved_material_until_successful_retry(selected, monkeypatch, redirect):
    root, vault = selected
    base = vault.parent / 'selected-base'
    base.mkdir()
    vault.rename(base / 'Vault')
    vault = base / 'Vault'
    obsidian.save_selection(root, vault, ['Work'], replace=True)
    approve(root)
    source_hooks.fetch(root)
    original = source_hooks.collect(root, 'obsidian', {}, 10, 10000).items[0]['source']
    location = redirect.removesuffix('-loop')
    target = {'folder': vault / 'Work', 'vault': vault, 'ancestor': base}[location]
    alternate = base.parent / 'alternate'
    body_dir = alternate / {'folder': '', 'vault': 'Work', 'ancestor': 'Vault/Work'}[location]
    body_dir.mkdir(parents=True)
    (body_dir / 'Secret.md').write_text('unselected secret', encoding='utf-8')
    preserved = target.with_name(target.name + '-preserved')
    target.rename(preserved)
    target.symlink_to(target if redirect.endswith('-loop') else alternate, target_is_directory=True)
    with monkeypatch.context() as guarded:
        guarded.setattr(obsidian.vault_reader, '_read_markdown',
                        lambda *a: pytest.fail('redirected acquisition read note content'))
        result = source_hooks.fetch(root)['obsidian']
    assert result['ok'] is False and result['allow_saved'] is False
    assert source_hooks.cited(root, original) is None
    with pytest.raises(source_hooks.SourceUnavailable):
        source_hooks.collect(root, 'obsidian', {}, 10, 10000)
    assert len(obsidian_store.latest_snapshots(root)) == 1
    target.unlink()
    preserved.rename(target)
    # Restoring the path alone must not clear the saved blocking receipt.
    assert source_hooks.cited(root, original) is None
    assert source_hooks.fetch(root)['obsidian']['ok'] is True
    assert source_hooks.cited(root, original)['excerpt'] == 'Atlas first version'


def test_temporary_missing_folder_keeps_explicitly_stale_saved_material(selected):
    root, vault = selected
    approve(root)
    source_hooks.fetch(root)
    original = source_hooks.collect(root, 'obsidian', {}, 10, 10000).items[0]['source']
    folder = vault / 'Work'
    folder.rename(vault / 'offline')
    result = source_hooks.fetch(root)['obsidian']
    assert result['ok'] is False and result['allow_saved'] is True
    assert source_hooks.cited(root, original)['excerpt'] == 'Atlas first version'
    assert source_hooks.stale_notice(root, 'obsidian', service.subscriptions(root)['obsidian'])
    (vault / 'offline').rename(folder)
    assert source_hooks.fetch(root)['obsidian']['ok'] is True


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks require privileges on Windows")
@pytest.mark.parametrize('nested', [False, True])
def test_configuration_rejects_looped_paths_without_changing_selection(selected, nested):
    root, vault = selected
    before = service.subscriptions(root)['obsidian']
    loop = vault.parent / 'loop'
    loop.symlink_to(loop, target_is_directory=True)
    path = loop / 'Vault' if nested else loop
    with pytest.raises((RemError, ValueError)):
        source_hooks.configure(root, 'obsidian', vault=str(path), folders=['Work'], replace=True)
    assert service.subscriptions(root)['obsidian'] == before
    assert not state_path(root, obsidian_store.DATABASE).exists()


@pytest.mark.parametrize('change', ['scope', 'model', 'disabled'])
def test_selection_change_during_scan_prevents_snapshot_publication(selected, monkeypatch, change):
    from connectonion.rem import config
    root, vault = selected
    approve(root)
    source_hooks.fetch(root)
    original = obsidian_store.latest_snapshots(root)[0]['source_id']
    (vault / 'Work' / 'Atlas.md').write_text('unpublished changed version', encoding='utf-8')
    real_list = obsidian.list_notes
    def scan_then_change(selection):
        notes = real_list(selection)
        if change == 'scope':
            obsidian.save_selection(root, vault, ['Private'])
        elif change == 'model':
            config.set_config(root, ['models.level3', 'different-model'])
        else:
            service.toggle_source(root, 'obsidian', False)
        return notes
    monkeypatch.setattr(obsidian, 'list_notes', scan_then_change)
    result = source_hooks.fetch(root)['obsidian']
    assert result['ok'] is False and result['allow_saved'] is False
    from contextlib import closing
    import sqlite3
    with closing(sqlite3.connect(state_path(root, obsidian_store.DATABASE))) as db:
        assert db.execute('SELECT source_id FROM snapshots').fetchall() == [(original,)]


def test_offline_hooks_do_not_wait_for_an_active_acquisition_writer(selected, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    root, _ = selected
    approve(root)
    source_hooks.fetch(root)
    original = source_hooks.collect(root, 'obsidian', {}, 10, 10000).items[0]['source']
    scanning, release = Event(), Event()
    real_list = obsidian.list_notes
    def held_scan(selection):
        scanning.set()
        assert release.wait(5), 'offline reader must complete before releasing writer'
        return real_list(selection)
    monkeypatch.setattr(obsidian, 'list_notes', held_scan)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(source_hooks.fetch, root)
        try:
            assert scanning.wait(5)
            with maintenance_lock(root):
                assert source_hooks.collect(root, 'obsidian', {}, 10, 10000).items
                assert source_hooks.cited(root, original)['excerpt'] == 'Atlas first version'
        finally:
            release.set()
        assert pending.result(timeout=5)['obsidian']['ok'] is True


def test_busy_notebook_keeps_obsidian_saved_material_available(selected, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from connectonion.rem import files
    root, _ = selected
    approve(root)
    source_hooks.fetch(root)
    original = source_hooks.collect(root, 'obsidian', {}, 1, 10000).items[0]['source']
    monkeypatch.setattr(files, 'WRITE_WAIT_SECONDS', 0.02)
    monkeypatch.setattr(source_hooks, 'ACQUISITION_WAIT_SECONDS', 0.02)
    holding, release = Event(), Event()
    def maintain():
        with maintenance_lock(root):
            holding.set()
            assert release.wait(5), 'source waited on a busy notebook'
    with ThreadPoolExecutor(max_workers=1) as pool:
        holder = pool.submit(maintain)
        try:
            assert holding.wait(2)
            result = source_hooks.fetch(root)['obsidian']
            assert result['ok'] is False and result['allow_saved'] is True
            assert read_json(state_path(root, 'source-acquisition.json'), {})['obsidian']['allow_saved'] is True
        finally:
            release.set()
        holder.result(timeout=2)
    assert source_hooks.cited(root, original)['excerpt'] == 'Atlas first version'
