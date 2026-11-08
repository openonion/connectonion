"""Nightly translation consent, ordering and the status promise use one queue."""
import os

import pytest

from connectonion.rem import daily, native_round, service, translate
from connectonion.rem.config import prepare, read_config, set_config
from connectonion.rem.files import Notebook, state_path, write_json


@pytest.fixture
def nightly(tmp_path, monkeypatch, rem_clock):
    prepare(tmp_path)
    set_config(tmp_path, ['languages', 'zh', 'limits.translations_per_day', '4'])
    monkeypatch.setattr('connectonion.rem.runner.ready', lambda config: ('', ''))
    monkeypatch.setattr('connectonion.rem.quota.read', lambda config: {'unknown': 'fixture'})
    day = service.notebook_today(tmp_path).isoformat()
    pages = {
        'people/mara.md': f'# Mara\n\n## Open threads\n- You owe Mara a reply since {day}.\n',
        'orgs/fern.md': f'# Fern\n\n## Open threads\n- You owe Fern a review since {day}.\n',
        'people/avery.md': '# Avery\n\n## Open threads\n- Avery owes you an answer.\n',
        'projects/recent.md': '# Recent\n\nThe pilot changed.\n',
        'people/done.md': '# Done\n\n## Open threads\n- You owe a reply.\n',
        'people/quiet.md': '# Quiet\n\n## Open threads\n- You owe a reply since 2020-01-01.\n',
    }
    for index, (record, text) in enumerate(pages.items()):
        Notebook(tmp_path).write(record, text)
        os.utime(tmp_path / record, (100 + index, 100 + index))
    write_json(state_path(tmp_path, 'threads.json'), {
        'people/done.md\nYou owe a reply.': {'state': 'done'},
    })
    translate.request(tmp_path, 'people/avery.md', 'zh')
    return tmp_path


def test_nightly_backlog_prioritizes_waiting_pages_then_latest_changes(nightly):
    queue = translate.backlog(nightly, 'zh', changed=['people/avery.md', 'projects/recent.md'])
    assert set(queue[:2]) == {'people/mara.md', 'orgs/fern.md'}
    assert queue[2:] == ['people/quiet.md', 'people/done.md', 'projects/recent.md', 'people/avery.md']
    directory = nightly / 'translation-task'
    directory.mkdir()
    task = translate.prepare(nightly, queue[0], 'zh', directory=directory)
    translate.check(task, {'result': task['prose']})
    assert translate.backlog(nightly, 'zh') == queue[1:]


@pytest.mark.parametrize('path', ['daily', 'native'])
def test_scheduled_paths_follow_priority_with_remaining_daily_cap(nightly, path):
    write_json(state_path(nightly, 'runs/run_used.json'), {
        'id': 'run_used', 'phase': 'translate', 'started_at': service.now().isoformat(), 'runner_attempts': 1,
    })
    write_json(state_path(nightly, 'worker.json'), {'enabled': True})
    config, selected = read_config(nightly), []
    changed = ['people/avery.md', 'projects/recent.md']
    if path == 'daily':
        daily._translate_changed(nightly, config, {}, changed,
                                 lambda root, record, language: selected.append(record), lambda text: None)
    else:
        cursor = native_round.prepare_translation_round(nightly, config, scheduled=True)
        cursor['changed'] = changed
        for index in range(4):
            directory = nightly / f'task-{index}'
            directory.mkdir()
            task = native_round.prepare_translation(nightly, cursor, config, directory)
            if task is None:
                break
            selected.append(task['record'])
            translate.check(task['task'], {'result': task['task']['prose']})
            write_json(state_path(nightly, f'runs/run_translation_{index}.json'), {
                'id': f'run_translation_{index}', 'phase': 'translate',
                'started_at': service.now().isoformat(), 'runner_attempts': 1,
            })
    assert set(selected[:2]) == {'people/mara.md', 'orgs/fern.md'}
    assert selected[2:] == ['people/quiet.md']
    assert translate.attempts_today(nightly) == 4


@pytest.mark.parametrize('requested,scheduled', [(True, True), (False, True), (True, False)])
def test_status_names_tonights_queue_or_the_command_to_request_it(nightly, requested, scheduled):
    from connectonion.cli.commands.rem_status import _notebook, notebook as counts
    directory = nightly / 'cached-task'
    directory.mkdir()
    task = translate.prepare(nightly, 'people/mara.md', 'zh', directory=directory)
    translate.check(task, {'result': task['prose']})
    write_json(state_path(nightly, 'runs/run_used.json'), {
        'id': 'run_used', 'phase': 'translate', 'started_at': service.now().isoformat(), 'runner_attempts': 1,
    })
    if not requested:
        set_config(nightly, ['languages', ''])
        write_json(state_path(nightly, 'translation-requests.json'), {})
    value = {'root': str(nightly), 'configured': True, 'worker': {'enabled': scheduled},
             'next_run': 'tonight' if scheduled else None, 'translation_coverage': translate.coverage(nightly)}
    text = '\n'.join(_notebook(nightly, value, counts(nightly), lambda args: 'co rem ' + ' '.join(args)))
    assert '1 of 6 pages translated' in text
    if not requested:
        assert 'not requested' in text and 'co rem config set languages zh' in text
        assert 'queued for tonight' not in text
    elif scheduled:
        assert '1 of 6 pages translated · 3 queued for tonight' in text
    else:
        assert 'schedule off' in text and 'co rem start' in text
        assert 'queued for tonight' not in text


def test_status_shows_unrequested_zh_even_without_a_cache(tmp_path):
    prepare(tmp_path)
    Notebook(tmp_path).write('people/mara.md', '# Mara\n')
    assert translate.coverage(tmp_path)['zh'] == {
        'total': 1, 'translated': 0, 'requested': False, 'queued': 0,
    }


def test_status_allocates_one_remaining_budget_across_languages(nightly):
    set_config(nightly, ['languages', 'zh,ja'])
    report = translate.coverage(nightly)
    assert report['zh']['queued'] == 4 and report['ja']['queued'] == 0
    assert report['zh']['requested'] and report['ja']['requested']


@pytest.mark.parametrize('next_day', [False, True])
def test_status_forecasts_the_budget_on_the_next_run_day(nightly, monkeypatch, next_day):
    from datetime import datetime, timedelta, timezone
    moment = datetime(2026, 11, 8, 22, tzinfo=timezone.utc)
    monkeypatch.setattr(service, 'now', lambda: moment)
    set_config(nightly, ['schedule.timezone', 'UTC'])
    slot = moment + timedelta(hours=5 if next_day else 1)
    monkeypatch.setattr(service, '_state_line', lambda *args: ('running', slot.isoformat()))
    write_json(state_path(nightly, 'runs/run_full.json'), {
        'id': 'run_full', 'phase': 'translate', 'started_at': moment.isoformat(), 'runner_attempts': 4,
    })
    assert service.status(nightly)['translation_coverage']['zh']['queued'] == (4 if next_day else 0)


def test_detected_language_is_a_menu_suggestion_not_translation_consent(tmp_path):
    prepare(tmp_path)
    write_json(state_path(tmp_path, 'map.json'), {'owner': {'languages': {'languages': ['zh']}}})
    assert translate.languages(tmp_path) == []
    assert translate.coverage(tmp_path)['zh']['requested'] is False


def test_status_request_command_keeps_other_requested_languages(nightly):
    from connectonion.cli.commands.rem_status import _notebook, notebook as counts
    set_config(nightly, ['languages', 'ja'])
    write_json(state_path(nightly, 'translation-requests.json'), {})
    value = {'root': str(nightly), 'configured': True, 'worker': {'enabled': True},
             'next_run': 'tonight', 'translation_coverage': translate.coverage(nightly)}
    text = '\n'.join(_notebook(nightly, value, counts(nightly), lambda args: 'co rem ' + ' '.join(args)))
    assert 'co rem config set languages ja,zh' in text
