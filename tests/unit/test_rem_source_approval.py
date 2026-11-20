"""Approval follows the displayed selection and every effective model route."""

from copy import deepcopy
from datetime import timedelta

import pytest

from connectonion.cli.commands.rem_output import render
from connectonion.rem import config, inquiry, service, source_hooks as hooks
from connectonion.rem.files import RemError, read_json, state_path, write_json
from tests.unit.rem_source_fixtures import citation, shared_sources


@pytest.mark.parametrize('change,reason', [
    ('new', 'no saved approval'), ('scope', 'selected scope changed'),
    ('model', 'model or execution route changed'), ('route', 'model or execution route changed'),
])
def test_status_explains_source_approval_without_loading_provider(shared_sources, monkeypatch, change, reason):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    env = shared_sources
    env.select('notes', approve=change != 'new')
    if change == 'scope':
        hooks.configure(env.root, 'notes', folders=['Private'])
    elif change == 'model':
        config.set_config(env.root, ['models.level2', 'different-model'])
    elif change == 'route':
        inquiry.set_route(env.root, 'extract', 'coai', 'different-model')
    monkeypatch.setattr(hooks, '_load', lambda *a: pytest.fail('status imported a provider'))
    state = service.status(env.root, include_coverage=False)
    assert reason in state['registered_sources']['notes']['status']
    output = CliRunner().invoke(app, ['rem', '--root', str(env.root), 'status'])
    assert output.exit_code == 0, output.output
    assert reason in output.output and 'co rem start' in output.output


@pytest.mark.parametrize('allow_saved,message', [
    (False, 'saved material blocked'), (True, 'saved material may be stale'),
])
def test_status_distinguishes_approval_from_acquisition_health(shared_sources, monkeypatch, allow_saved, message):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    env.failures['notes'] = hooks.SourceUnavailable('service unavailable', allow_saved=allow_saved)
    hooks.fetch(env.root)
    monkeypatch.setattr(hooks, '_load', lambda *a: pytest.fail('status imported provider'))
    output = CliRunner().invoke(app, ['rem', '--root', str(env.root), 'status'])
    assert output.exit_code == 0, output.output
    assert message in ' '.join(output.output.split())
    assert 'collect --source notes' in ' '.join(output.output.split())


@pytest.mark.parametrize('level', list(config.LEVEL_MODELS))
def test_each_model_level_change_requires_fresh_source_approval(shared_sources, level):
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    items = hooks.collect(env.root, 'notes', {}, 2, 10000).items
    before = service.summary_fingerprint(env.root)
    config.set_config(env.root, ['models.' + level, 'different-model'])
    assert service.summary_fingerprint(env.root) != before
    assert not hooks.approved(env.root, 'notes')
    assert hooks.fetch(env.root) == {}
    with pytest.raises(hooks.SourceMaterialUnavailable):
        hooks.guard_turn(env.root, items, lambda: pytest.fail('sent to unapproved model'))()
    shown = []
    assert service.ensure_consent(env.root, confirm=lambda summary: shown.append(summary) or True)
    assert shown and hooks.approved(env.root, 'notes')
    assert 'different-model' in render(shown[0], 'start — source access and schedule')
    assert service.ensure_consent(env.root, confirm=lambda summary: pytest.fail('repeat approval'))


@pytest.mark.parametrize('stage', ['extract', 'plan', 'synthesize', 'render', 'claim-audit'])
def test_stage_route_and_clear_revoke_saved_material(shared_sources, stage):
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    before = service.summary_fingerprint(env.root)
    inquiry.set_route(env.root, stage, 'coai', 'route-model')
    assert service.summary_fingerprint(env.root) != before
    assert hooks.cited(env.root, citation('notes')) is None
    summary = service.consent_summary(env.root)
    assert summary['source_execution']['stages'][stage] == {'runner': 'coai', 'model': 'route-model'}
    text = render(summary, 'start — source access and schedule')
    assert stage in text and 'coai' in text and 'route-model' in text
    assert service.ensure_consent(env.root, confirm=lambda summary: True)
    assert hooks.cited(env.root, citation('notes')) is not None
    inquiry.clear_route(env.root, stage)
    assert not hooks.approved(env.root, 'notes')


@pytest.mark.parametrize('change', ['scope', 'model', 'route', 'remove', 'add'])
def test_confirmation_cannot_approve_configuration_changed_while_displayed(shared_sources, change):
    env = shared_sources
    env.select('notes', approve=False)

    def confirm(summary):
        assert summary['sources']['notes']['scope']['folders'] == ['Work']
        if change == 'scope':
            hooks.configure(env.root, 'notes', folders=['Private'])
        elif change == 'model':
            config.set_config(env.root, ['models.level2', 'different-model'])
        elif change == 'route':
            inquiry.set_route(env.root, 'extract', 'coai', 'different-model')
        elif change == 'remove':
            service.toggle_source(env.root, 'notes', False)
        else:
            hooks.configure(env.root, 'tasks')
        return True

    with pytest.raises(RemError, match='changed during confirmation'):
        service.ensure_consent(env.root, confirm=confirm)
    assert not hooks.approved(env.root, 'notes')
    assert not hooks.approved(env.root, 'tasks')
    assert hooks.fetch(env.root) == {}
    assert not state_path(env.root, 'consent.json').exists()


def test_callback_cannot_rewrite_the_snapshot_it_is_approving(shared_sources):
    env = shared_sources
    env.select('notes', approve=False)

    def confirm(summary):
        hooks.configure(env.root, 'notes', folders=['Private'])
        summary['sources']['notes']['scope']['folders'][:] = ['Private']
        return True

    with pytest.raises(RemError, match='changed during confirmation'):
        service.ensure_consent(env.root, confirm=confirm)
    assert not hooks.approved(env.root, 'notes')


def test_fresh_default_sources_do_not_change_just_because_confirmation_takes_time(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'mail_available', lambda kind: False)
    monkeypatch.setattr(config, 'first_runner', lambda value: value)
    config.prepare(tmp_path)
    initial = service.now()
    monkeypatch.setattr(service, 'now', lambda: initial)
    shown = []

    def confirm(summary):
        shown.append(deepcopy(summary))
        monkeypatch.setattr(service, 'now', lambda: initial + timedelta(minutes=5))
        return True

    assert service.ensure_consent(tmp_path, confirm=confirm)
    assert shown[0]['sources']['codex']['since'] == service.consent_summary(tmp_path)['sources']['codex']['since']
    assert service.ensure_consent(tmp_path, confirm=lambda summary: pytest.fail('repeat approval'))


def test_mail_offered_in_the_snapshot_is_subscribed_only_after_confirmation(shared_sources, monkeypatch):
    env = shared_sources
    env.select('notes', approve=False)
    saved = read_json(state_path(env.root, 'subscriptions.json'), {})
    saved['gmail'].update(enabled=False, consented=False, unsubscribed=False)
    write_json(state_path(env.root, 'subscriptions.json'), saved)
    monkeypatch.setattr(service, 'mail_available', lambda kind: kind == 'gmail')

    def confirm(summary):
        assert 'if you approve' in summary['sources']['gmail']['state']
        assert not service.subscriptions(env.root)['gmail']['enabled']
        return True

    assert service.ensure_consent(env.root, confirm=confirm)
    assert service.subscriptions(env.root)['gmail']['consented']
    assert hooks.approved(env.root, 'notes')
    assert service.ensure_consent(env.root, confirm=lambda summary: pytest.fail('repeat approval'))


@pytest.mark.parametrize('change', ['model', 'scope', 'route', 'unchanged'])
def test_new_init_mailbox_never_reapproves_other_sources(shared_sources, monkeypatch, change):
    env = shared_sources
    service.grant_init_sources(env.root)
    env.select('notes')
    path = state_path(env.root, 'consent.json')
    original = deepcopy(read_json(path, {})['source_approvals'])
    if change == 'model':
        config.set_config(env.root, ['models.level3', 'different-model'])
    elif change == 'scope':
        hooks.configure(env.root, 'notes', folders=['Private'])
    elif change == 'route':
        inquiry.set_route(env.root, 'extract', 'coai', 'different-model')
    saved = read_json(state_path(env.root, 'subscriptions.json'), {})
    saved['gmail'].update(enabled=False, consented=False, unsubscribed=False)
    write_json(state_path(env.root, 'subscriptions.json'), saved)
    monkeypatch.setattr(service, 'mail_available', lambda kind: kind == 'gmail')
    service.refresh_init_mailboxes(env.root)
    assert service.subscriptions(env.root)['gmail']['consented']
    assert read_json(path, {})['source_approvals'] == original
    assert hooks.approved(env.root, 'notes') is (change == 'unchanged')
    if change != 'unchanged':
        assert not service.ensure_consent(env.root, confirm=lambda summary: False)
        assert not hooks.approved(env.root, 'notes')
        shown = []
        assert service.ensure_consent(env.root, confirm=lambda summary: shown.append(summary) or True)
        assert shown and 'Sources:' in render(shown[0], 'start — source access and schedule')
        assert hooks.approved(env.root, 'notes')


def test_legacy_summary_alone_does_not_authorize_current_model_routes(shared_sources):
    env = shared_sources
    env.select('notes')
    path = state_path(env.root, 'consent.json')
    receipt = read_json(path, {})
    receipt.pop('source_approvals')
    write_json(path, receipt)
    assert not hooks.approved(env.root, 'notes')
    assert hooks.fetch(env.root) == {}
    assert service.ensure_consent(env.root, confirm=lambda summary: True)
    assert hooks.approved(env.root, 'notes')


def test_a_running_turn_cannot_resume_after_routes_are_changed_and_reapproved(shared_sources):
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    items = hooks.collect(env.root, 'notes', {}, 2, 10000).items
    old = inquiry.stage_config(env.root, config.read_config(env.root), 'extract')
    calls = []
    guarded = hooks.guard_turn(env.root, items, lambda *args: calls.append(args[2]['model']))
    guarded(env.root, 'synthetic prompt', old, 'extract')
    config.set_config(env.root, ['models.level2', 'different-model'])
    service.ensure_consent(env.root, confirm=lambda summary: True)
    assert hooks.approved(env.root, 'notes')
    with pytest.raises(hooks.SourceMaterialUnavailable, match='execution routes changed'):
        guarded(env.root, 'follow-up', old, 'extract')
    fresh = inquiry.stage_config(env.root, config.read_config(env.root), 'extract')
    hooks.guard_turn(env.root, items, lambda *args: calls.append(args[2]['model']))(
        env.root, 'new task', fresh, 'extract')
    assert calls == [old['model'], 'different-model']


@pytest.mark.parametrize('entry', ['extract', 'inquiry', 'runner'])
def test_preparation_rejects_a_cached_stage_model_even_if_it_is_approved_for_other_stages(shared_sources, entry):
    from connectonion.rem import extract, runner
    from connectonion.rem.files import Notebook
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    items = hooks.collect(env.root, 'notes', {}, 2, 10000).items
    old = config.read_config(env.root)
    config.set_config(env.root, ['models.level2', 'different-model'])
    service.ensure_consent(env.root, confirm=lambda summary: True)
    assert hooks.approved(env.root, 'notes')
    directory = state_path(env.root, 'tasks/old-input')
    directory.mkdir(parents=True)
    with pytest.raises(hooks.SourceMaterialUnavailable, match='execution routes changed'):
        if entry == 'extract':
            extract.run_extract(items, old, 'notes', root=env.root)
        elif entry == 'inquiry':
            inquiry.prepare(env.root, directory, items, old, 'plan')
        else:
            runner.prepare(Notebook(env.root), items, old, 'notes', stage='extract', directory=directory)


@pytest.mark.parametrize('legacy', [False, True])
def test_saved_task_cannot_reuse_old_execution_routes_after_fresh_approval(shared_sources, legacy):
    env = shared_sources
    env.select('notes')
    hooks.fetch(env.root)
    items = hooks.collect(env.root, 'notes', {}, 2, 10000).items
    directory = state_path(env.root, 'tasks/retained')
    write_json(directory / 'material.json', items)
    task = {'directory': str(directory), 'task': {'items': items, 'source_stage': 'extract',
            'config': inquiry.stage_config(env.root, config.read_config(env.root), 'extract'),
            'source_execution': hooks.execution_stamp(env.root, items)}}
    hooks.task_material(env.root, task)
    if legacy:
        task['task'].pop('source_execution')
    config.set_config(env.root, ['models.level2', 'different-model'])
    service.ensure_consent(env.root, confirm=lambda summary: True)
    with pytest.raises(hooks.SourceMaterialUnavailable, match='execution routes changed'):
        hooks.task_material(env.root, task)


def test_approved_render_route_can_finish_an_investigation(shared_sources, monkeypatch):
    from connectonion.rem import runner
    from connectonion.rem.files import Notebook
    env = shared_sources
    inquiry.set_route(env.root, 'render', 'coai', 'render-model')
    env.select('notes')
    hooks.fetch(env.root)
    items = hooks.collect(env.root, 'notes', {}, 2, 10000).items
    book = Notebook(env.root)
    record = 'people/atlas.md'
    book.stub_person(record, 'Atlas')
    before = book.read(record)
    items.append({'role': 'page', 'record': record, 'one_page': True,
                  'source': 'investigation:page', 'text': before})
    used = []

    def execute(workdir, prompt, selected, stage, **options):
        used.append((selected['runner'], selected['model']))
        next(workdir.glob('investigate-*/candidate.md')).write_text(before, encoding='utf-8')
        return {'result': 'NO CHANGE', 'usage': {}}

    monkeypatch.setattr(runner, 'run_task', execute)
    monkeypatch.setattr(inquiry, 'run', lambda *args, **kwargs: {'usage': {}})
    result = runner.run_stage(book, items, config.read_config(env.root), 'notes', stage='investigate')
    assert used == [('coai', 'render-model')]
    assert result['changed'] == [] and book.read(record) == before
