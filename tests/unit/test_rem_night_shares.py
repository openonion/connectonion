"""Every stage gets its share of a night (owner, 2026-11-16).

A queue of 333 investigations against a weekly budget for 60 to 90 kept the round
in its job queue: Abstract and Deepen stood at 0 after eight catchup runs. A night
now investigates its share and goes on; the pages that did not fit wait for a later
night and none are dropped. Fictional people only.
"""
import json

import pytest
import yaml
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import catchup, daily, native, native_round, night, quota, service, stages
from connectonion.rem.config import default_config, prepare, read_config, set_config
from connectonion.rem.files import Notebook, read_json, state_path, write_json

WAITING = 'investigation-waiting.json'


@pytest.fixture
def notebook(tmp_path, monkeypatch, rem_clock):
    prepare(tmp_path)
    set_config(tmp_path, ['schedule.timezone', 'UTC'])
    write_json(state_path(tmp_path, 'subscriptions.json'), {})
    write_json(state_path(tmp_path, 'consent.json'), {'authorized_at': service.now().isoformat()})
    monkeypatch.setattr(daily, '_clients', lambda sources: {})
    monkeypatch.setattr(night, 'prepare', lambda *a, **k: [])
    monkeypatch.setattr('connectonion.rem.tasks.auto_dispatch', lambda *a: [])
    return tmp_path


def person(name):
    return {'record': f'people/{name}.md', 'kind': 'person'}


def skill(name):
    return {'record': f'skills/catalog/{name}.md', 'kind': 'skill'}


def cursor_of(root, jobs, **fields):
    run, path = daily._reserve(root, 'daily-update', 0, {})
    write_json(path, run)
    return {'phase': 'daily-update', 'batch': {'done': True}, 'current': None, 'jobs': jobs, 'job_index': 0,
            'summaries': [], 'same_new_left': 0, 'same_left': 0, 'slot': None, 'changed': [], 'translations': [],
            'started_at': service.now().isoformat(), 'run': run, **fields}


def serve(monkeypatch, nothing_new=()):
    """Each prepared job is one task; a page in `nothing_new` is passed over, as a page with no new mail is."""
    def prepared(root, cursor, config, directory):
        job = cursor['jobs'][cursor['job_index']]
        if job['record'] in nothing_new:
            cursor['job_index'] += 1
            return None
        return {'stage': 'investigate', 'record': job['record']}
    monkeypatch.setattr(native_round, '_prepare_job', prepared)


def walk(root, cursor):
    """Take tasks until the round has no more, finishing each page as its accepted task does."""
    directory = root / 'task'
    directory.mkdir(exist_ok=True)
    served = []
    while True:
        task = native_round.prepare_task(root, cursor, read_config(root), directory)
        if task is None:
            return served
        served.append(task['record'])
        cursor['job_index'] += 1


def test_the_new_limits_default_for_a_notebook_saved_before_them(tmp_path):
    limits = default_config()['limits']
    assert limits['investigations_per_night'] == 12 and limits['skill_pages_per_night'] == 3
    old = default_config()
    old.pop('model')
    for name in ('investigations_per_night', 'skill_pages_per_night'):
        old['limits'].pop(name)
    saved = yaml.safe_dump(old)
    tmp_path.joinpath('config.yaml').write_text(saved)
    limits = read_config(tmp_path)['limits']
    assert limits['investigations_per_night'] == 12 and limits['skill_pages_per_night'] == 3
    assert tmp_path.joinpath('config.yaml').read_text() == saved  # read, never rewritten
    assert set_config(tmp_path, ['limits.investigations_per_night', '20'])['limits']['investigations_per_night'] == 20


def test_a_night_investigates_its_share_then_goes_on_and_keeps_the_rest_waiting(notebook, monkeypatch):
    serve(monkeypatch)
    set_config(notebook, ['limits.investigations_per_night', '2'])
    people = [person(name) for name in ('ivy', 'wren', 'fern', 'heron', 'lark')]
    cursor = cursor_of(notebook, list(people))
    assert walk(notebook, cursor) == ['people/ivy.md', 'people/wren.md']
    # The round went past its queue to its other stages and completed: deepen may run.
    assert cursor['done'] and cursor['run']['outcome'] == 'completed'
    saved = read_json(state_path(notebook, WAITING), {})
    assert saved['jobs'] == people[2:]
    assert saved['investigations'] == {'done': 2, 'limit': 2, 'waiting': 3}
    assert saved['skill_pages']['waiting'] == 0


def test_a_page_passed_over_does_not_use_the_share(notebook, monkeypatch):
    serve(monkeypatch, nothing_new={'people/ivy.md', 'people/fern.md'})
    set_config(notebook, ['limits.investigations_per_night', '2'])
    cursor = cursor_of(notebook, [person(name) for name in ('ivy', 'wren', 'fern', 'heron', 'lark')])
    assert walk(notebook, cursor) == ['people/wren.md', 'people/heron.md']
    assert read_json(state_path(notebook, WAITING), {})['jobs'] == [person('lark')]


def test_a_page_already_open_keeps_going_after_the_share_is_used(notebook, monkeypatch):
    serve(monkeypatch)
    set_config(notebook, ['limits.investigations_per_night', '1'])
    cursor = cursor_of(notebook, [person('ivy'), person('wren')])
    directory = notebook / 'task'
    directory.mkdir()
    for _ in range(3):  # three rounds of one page: one investigation
        task = native_round.prepare_task(notebook, cursor, read_config(notebook), directory)
        assert task['record'] == 'people/ivy.md'
    cursor['job_index'] += 1
    assert native_round.prepare_task(notebook, cursor, read_config(notebook), directory) is None
    assert read_json(state_path(notebook, WAITING), {})['investigations'] == {'done': 1, 'limit': 1, 'waiting': 1}


def test_skill_pages_have_their_own_share_and_follow_the_other_pages(notebook, monkeypatch):
    serve(monkeypatch)
    set_config(notebook, ['limits.investigations_per_night', '2', 'limits.skill_pages_per_night', '1'])
    book = Notebook(notebook)
    queue = [skill('deploy'), person('ivy'), skill('review'), {'record': 'orgs/lantern.md', 'kind': 'older'},
             {'record': 'people/wren.md', 'kind': 'retry', 'entry': {}}, person('fern')]
    for job in queue:
        book.write(job['record'], '# Fixture\n')
    monkeypatch.setattr(native_round, '_jobs', lambda *a, **k: [dict(job) for job in queue])
    cursor = native_round.prepare(notebook, read_config(notebook), scheduled=False)
    cursor.update(batch={'done': True}, summaries=[], same_left=0, same_new_left=0)
    # Older pages and retries are in the main share; skill pages never take a place in it.
    assert walk(notebook, cursor) == ['people/ivy.md', 'orgs/lantern.md', 'skills/catalog/deploy.md']
    saved = read_json(state_path(notebook, WAITING), {})
    assert [job['record'] for job in saved['jobs']] == ['people/wren.md', 'people/fern.md', 'skills/catalog/review.md']
    assert saved['investigations'] == {'done': 2, 'limit': 2, 'waiting': 2}
    assert saved['skill_pages'] == {'done': 1, 'limit': 1, 'waiting': 1}


def test_the_next_night_continues_with_the_pages_that_waited(notebook, monkeypatch):
    serve(monkeypatch)
    set_config(notebook, ['limits.investigations_per_night', '2'])
    book = Notebook(notebook)
    people = [person(name) for name in ('ivy', 'wren', 'fern', 'heron', 'lark')]
    for job in people:
        book.write(job['record'], '# Fixture\n')
    with catchup.scope(notebook, 1):
        assert walk(notebook, cursor_of(notebook, list(people), catchup_night=1)) == ['people/ivy.md', 'people/wren.md']
    # The next round's own listing finds only one of them due (the others' mail predates the last round).
    monkeypatch.setattr(native_round, '_jobs', lambda *a, **k: [person('sorrel'), person('heron')])
    book.write('people/sorrel.md', '# Fixture\n')
    book.path('people/lark.md').unlink()  # merged away since: not carried
    with catchup.scope(notebook, 2):
        cursor = native_round.prepare(notebook, read_config(notebook), scheduled=False)
        # The page only the waiting list remembers leads; a page listed again keeps its listed place, once.
        assert [job['record'] for job in cursor['jobs']] == ['people/fern.md', 'people/sorrel.md', 'people/heron.md']
        cursor.update(batch={'done': True}, summaries=[], same_left=0, same_new_left=0)
        assert walk(notebook, cursor) == ['people/fern.md', 'people/sorrel.md']
    assert read_json(state_path(notebook, WAITING), {})['jobs'] == [person('heron')]
    with catchup.scope(notebook, 3):
        monkeypatch.setattr(native_round, '_jobs', lambda *a, **k: [])
        cursor = native_round.prepare(notebook, read_config(notebook), scheduled=False)
        cursor.update(batch={'done': True}, summaries=[], same_left=0, same_new_left=0)
        assert walk(notebook, cursor) == ['people/heron.md']
    assert read_json(state_path(notebook, WAITING), {})['jobs'] == []


def test_a_later_round_of_the_same_night_does_not_get_a_second_share(notebook, monkeypatch):
    serve(monkeypatch)
    set_config(notebook, ['limits.investigations_per_night', '1'])
    people = [person('ivy'), person('wren')]
    for job in people:
        Notebook(notebook).write(job['record'], '# Fixture\n')
    assert walk(notebook, cursor_of(notebook, list(people))) == ['people/ivy.md']
    monkeypatch.setattr(native_round, '_jobs', lambda *a, **k: [])
    cursor = native_round.prepare(notebook, read_config(notebook), scheduled=False)
    cursor.update(batch={'done': True}, summaries=[], same_left=0, same_new_left=0)
    assert walk(notebook, cursor) == []
    assert read_json(state_path(notebook, WAITING), {})['jobs'] == [person('wren')]


def test_status_says_the_share_was_used_and_how_many_pages_wait(notebook, monkeypatch):
    serve(monkeypatch)
    set_config(notebook, ['limits.investigations_per_night', '1'])
    row = next(row for row in stages.status(notebook, read_config(notebook), []) if row['name'] == 'Investigate')
    assert 'later nights' not in row['text']
    walk(notebook, cursor_of(notebook, [person('ivy'), person('wren'), person('fern')]))
    row = next(row for row in stages.status(notebook, read_config(notebook), []) if row['name'] == 'Investigate')
    assert "1 of the last night's 1 investigations done; 2 wait for later nights" in row['text']
    assert row['shares']['investigations'] == {'done': 1, 'limit': 1, 'waiting': 2}


def test_catchup_counts_carry_the_nights_shares(notebook, monkeypatch):
    serve(monkeypatch)
    set_config(notebook, ['limits.investigations_per_night', '1'])
    with catchup.scope(notebook, 4):
        cursor = cursor_of(notebook, [person('ivy'), person('wren')], catchup_night=4)
        walk(notebook, cursor)
        write_json(state_path(notebook, 'round.json'), cursor)
    assert catchup._counts(notebook, 4)['shares']['investigations'] == {'done': 1, 'limit': 1, 'waiting': 1}
    assert catchup._counts(notebook, 5)['shares'] == {}  # another night's shares are not this night's


def test_the_nights_line_says_what_waits_in_words(notebook, monkeypatch):
    row = {'mail': 0, 'sessions': 0, 'written': 12, 'decisions': 1, 'translated': 2, 'drafts': 0, 'changed': [],
           'parked': [], 'deepened': 3, 'deepen_reason': '',
           'shares': {'investigations': {'done': 12, 'limit': 12, 'waiting': 319},
                      'skill_pages': {'done': 3, 'limit': 3, 'waiting': 1}}}

    def run(root, *, nights, progress, stage, say):
        progress(1, row)
        return {'nights': [row], 'reason': '', 'failed': False, 'held': None, 'parked': [], 'candidates': '',
                'deepen_reason': '', **{name: row[name] for name in
                                        ('mail', 'sessions', 'written', 'decisions', 'translated', 'drafts', 'deepened')}}

    monkeypatch.setattr(catchup, 'run', run)
    result = CliRunner().invoke(app, ['rem', '--root', str(notebook), 'catchup'])
    assert result.exit_code == 0, result.output
    line = next(line for line in result.output.splitlines() if line.startswith('Night 1:'))
    assert ("3 pages deepened · 12 of tonight's 12 investigations done; 319 wait for later nights"
            " · 3 of tonight's 3 skill pages done; 1 waits for later nights") in line


def test_a_round_whose_pages_are_all_parked_still_saves_the_calendar_and_the_day_plan(notebook, monkeypatch):
    def blocked(root, **options):
        write_json(state_path(root, 'round.json'), {'done': True, 'catchup_night': catchup.number(root),
                                                    'started_at': service.now().isoformat(), 'run': {'id': 'run_fixture'}})
        raise native_round.RoundBlocked('All remaining candidates are parked: people/ivy.md: Outlook timed out')

    monkeypatch.setattr(native, '_next_task', blocked)
    monkeypatch.setattr(quota, 'read', lambda config: {'unknown': 'fixture'})
    result = CliRunner().invoke(app, ['rem', '--root', str(notebook), '--json', 'catchup'])
    assert result.exit_code == 1, result.output
    value = json.loads(result.stdout)
    night_row = (value.get('data') or value)['nights'][0]
    assert night_row['day_plan']['dates'] == ['2026-09-07', '2026-09-08']
    assert read_json(state_path(notebook, 'round.json'), {})['calendar']['day_plan'] == night_row['day_plan']
