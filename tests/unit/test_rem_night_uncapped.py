"""D-104: count caps no longer stop the night; only the Codex week floor does. Fictional people only."""
import pytest

from connectonion.rem import daily, native_round, night
from connectonion.rem.config import default_config, prepare, read_config, set_config
from connectonion.rem.files import Notebook, RemError, read_json, state_path, write_json
from tests.unit.test_rem_proactive import fake_night_writer, night_item


@pytest.fixture
def notebook(tmp_path, monkeypatch, rem_clock):
    prepare(tmp_path)
    monkeypatch.setattr(daily, '_clients', lambda sources: {})
    return tmp_path


RETIRED = ('tasks_per_night', 'drafts_per_night', 'jobs_per_round', 'translations_per_day')


def test_count_caps_are_retired_and_a_saved_one_is_dropped(notebook):
    import yaml
    assert not set(RETIRED) & set(default_config()['limits'])
    saved = yaml.safe_load((notebook / 'config.yaml').read_text())
    saved['limits'].update(tasks_per_night=3, drafts_per_night=10, jobs_per_round=8, translations_per_day=100)
    (notebook / 'config.yaml').write_text(yaml.safe_dump(saved))
    assert not set(RETIRED) & set(read_config(notebook)['limits'])
    for name in RETIRED:
        with pytest.raises(RemError, match='D-104'):
            set_config(notebook, [f'limits.{name}', '5'])


def test_every_owed_reply_gets_a_draft_with_no_nightly_cap(notebook, monkeypatch):
    from connectonion.rem import service
    for number in range(4):
        night_item(notebook, number)
    fake_night_writer(monkeypatch)
    # Thirty drafts already written tonight: the old drafts_per_night stopped here.
    write_json(state_path(notebook, 'runs/run_drafts.json'), {'phase': 'reply-draft', 'runner_attempts': 30,
                                                           'started_at': service.now().isoformat()})
    daily._draft_replies(notebook, read_config(notebook), {})
    assert [row['kind'] for row in night.listing(notebook)] == ['prepared'] * 4


def _cursor(**fields):
    return {'phase': 'daily-update', 'batch': {'done': True}, 'current': None,
            'jobs': [{'record': 'people/wren.md', 'kind': 'person'}], 'job_index': 0, 'summaries': [],
            'same_new_left': 0, 'same_left': 0, 'slot': None, 'changed': [], 'translations': [], **fields}


def _no_side_work(monkeypatch):
    monkeypatch.setattr(night, 'prepare', lambda *a, **k: [])
    monkeypatch.setattr('connectonion.rem.tasks.auto_dispatch', lambda *a: [])
    monkeypatch.setattr(native_round, 'finish', lambda *a: None)


def test_a_spent_investigation_portion_does_not_drop_the_rounds_jobs(notebook, monkeypatch):
    # rc62: at investigation_left 0 with no page open the round skipped every remaining job.
    _no_side_work(monkeypatch)
    monkeypatch.setattr(native_round, '_prepare_job', lambda root, cursor, config, directory: {'stage': 'investigate'})
    cursor = _cursor(investigation_left=0)
    directory = notebook / 'task'
    directory.mkdir()
    assert native_round.prepare_task(notebook, cursor, read_config(notebook), directory) == {'stage': 'investigate'}
    assert cursor['investigation_left'] == native_round.PORTION


def test_a_spent_portion_hands_a_backlog_sized_share_to_translation_then_resumes(notebook, monkeypatch):
    _no_side_work(monkeypatch)
    monkeypatch.setattr(native_round, '_prepare_job', lambda root, cursor, config, directory: {'stage': 'investigate'})
    set_config(notebook, ['languages', 'zh,en'])
    book = Notebook(notebook)
    for number in range(3):
        book.write(f'people/fern-{number}.md', f'# Fern {number}\n')
    assert native_round.translation_share(notebook) == 3  # never more turns than pages waiting
    cursor = _cursor(investigation_left=0)
    directory = notebook / 'task'
    directory.mkdir()
    first = native_round.prepare_task(notebook, cursor, read_config(notebook), directory)
    assert first['stage'] == 'translate' and cursor['translation_left'] == 2
    cursor['translation_left'] = 0
    assert native_round.prepare_task(notebook, cursor, read_config(notebook), directory) == {'stage': 'investigate'}
    assert 'translation_left' not in cursor and cursor['investigation_left'] == native_round.PORTION


def test_the_translation_share_grows_with_the_backlog(notebook, monkeypatch):
    from connectonion.rem import translate
    monkeypatch.setattr(translate, 'languages', lambda root: ['zh', 'en'])
    monkeypatch.setattr(translate, 'backlog', lambda root, language, changed=(): [f'people/p{i}.md' for i in range(1000)])
    # About 1,000 pages waiting: 20 translation turns for every 8 investigation turns.
    assert native_round.translation_share(notebook) == 20
