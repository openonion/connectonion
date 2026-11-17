"""Cheap stages are finished in a night, not rationed (owner, 2026-11-17).

"Translation and summaries cost little; there is so little content, it should all be
done. Why does catchup end before everything has run?" A translation turn measured 11
to 83 seconds and 9 of 9 were accepted first try, a session summary 24 to 57 seconds;
four real nights translated 9, 8, 9 and 0 of some 350 waiting pages, because the
closing pass took one share (a fiftieth of the backlog) and the round five summaries.
Fictional people only.
"""
import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import catchup, native, native_round, schedule, service, sessions, stages, translate
from connectonion.rem.config import default_config, read_config, set_config
from connectonion.rem.files import read_json, state_path, write_json
from tests.unit.test_rem_night_shares import HELD, WAITING, cursor_of, notebook, person, serve  # noqa: F401

PAGES = [f'people/fern-{number}.md' for number in range(12)]


def waiting_pages(monkeypatch, pages=PAGES):
    """`pages` wait for Chinese; a translation is a task once and its page is then done."""
    done = []
    monkeypatch.setattr(translate, 'languages', lambda root: ['zh', 'en'])
    monkeypatch.setattr(translate, 'claimed', lambda root: False)
    monkeypatch.setattr(translate, 'shown_today', lambda root: [])
    monkeypatch.setattr(translate, 'backlog', lambda root, language, **k: [page for page in pages if page not in done])
    monkeypatch.setattr(translate, 'prepare', lambda root, record, language, **k: {'language': language})
    return done


def night(root, cursor, done):
    """The stages a round serves until it is done, each translation settled as `advance` settles it."""
    directory = root / 'task'
    directory.mkdir(exist_ok=True)
    served = []
    while (task := native_round.prepare_task(root, cursor, read_config(root), directory)) is not None:
        served.append(task['stage'])
        if task['stage'] == 'translate':
            done.append(task['record'])
            cursor['translations'].append(task['record'])
            cursor.setdefault('translation_attempts', []).append(['zh', task['record']])
        elif task['stage'] == 'investigate':
            cursor['investigation_left'] -= 1
            cursor.update(job_index=cursor['job_index'] + 1, current=None)
    return served


def test_the_closing_translation_goes_on_until_no_page_waits(notebook, monkeypatch):
    done = waiting_pages(monkeypatch)
    # Investigation is held by its weekly budget, as on the four measured nights: no portion, no break.
    cursor = cursor_of(notebook, [person('ivy')], investigation_held=HELD)
    assert night(notebook, cursor, done) == ['translate'] * 12
    assert sorted(done) == sorted(PAGES) and cursor['done'] and cursor['run']['outcome'] == 'completed'
    assert 'translations_waiting' not in cursor


def test_a_round_translates_at_most_its_bound_and_keeps_how_many_wait(notebook, monkeypatch):
    done = waiting_pages(monkeypatch)
    set_config(notebook, ['limits.translations_per_round', '5'])
    cursor = cursor_of(notebook, [])
    assert night(notebook, cursor, done) == ['translate'] * 5
    # The round still ends, completed; what the bound left is said, not dropped.
    assert cursor['done'] and cursor['translations_waiting'] == 7


def test_the_bound_counts_the_translations_between_portions_too(notebook, monkeypatch):
    serve(monkeypatch)
    done = waiting_pages(monkeypatch)
    monkeypatch.setattr(native_round, 'translation_share', lambda root: 3)
    set_config(notebook, ['limits.translations_per_round', '4'])
    cursor = cursor_of(notebook, [person(name) for name in ('ivy', 'wren', 'fern')])
    served = night(notebook, cursor, done)
    assert served == ['investigate', 'investigate', 'translate', 'translate', 'translate', 'investigate', 'translate']


def test_a_page_whose_translation_failed_is_tried_once_and_the_rest_are_still_done(notebook, monkeypatch):
    done = waiting_pages(monkeypatch)
    cursor = cursor_of(notebook, [], translation_attempts=[['zh', PAGES[0]]], task_day=None)
    monkeypatch.setattr(native_round, '_reset_attempts', lambda root, cursor: None)
    assert night(notebook, cursor, done) == ['translate'] * 11 and PAGES[0] not in done


def test_the_share_between_portions_is_a_tenth_of_the_backlog_and_at_least_ten(notebook, monkeypatch):
    for waiting, share in ((3, 3), (40, 10), (325, 33), (1000, 100)):
        waiting_pages(monkeypatch, [f'people/p{number}.md' for number in range(waiting)])
        assert native_round.translation_share(notebook) == share


def test_a_round_takes_its_configured_number_of_session_summaries(notebook, monkeypatch):
    asked = []
    monkeypatch.setattr(sessions, '_summary_candidates', lambda root, limit: asked.append(limit) or [])
    assert default_config()['limits']['summaries_per_round'] == 40
    assert default_config()['limits']['translations_per_round'] == 400
    set_config(notebook, ['limits.summaries_per_round', '25'])
    native_round.prepare(notebook, read_config(notebook), scheduled=False)
    assert asked == [25]


def test_the_two_bounds_govern_future_work_so_a_prepared_task_does_not_hash_them():
    assert {'summaries_per_round', 'translations_per_round'} <= native.RUN_LIMITS


def test_a_round_with_no_portion_deepens_once_its_closing_translation_has_begun(notebook, monkeypatch):
    """Translation's whole backlog is hours; the deepen slot used to wait for the completed round."""
    done = waiting_pages(monkeypatch)
    cursor = cursor_of(notebook, [])
    directory = notebook / 'task'
    directory.mkdir()
    assert not schedule._depth_early(notebook, cursor)
    assert native_round.prepare_task(notebook, cursor, read_config(notebook), directory)['stage'] == 'translate'
    assert schedule._depth_early(notebook, cursor) and not cursor.get('portions')
    # One slot a round: not again once it is claimed.
    assert not schedule._depth_early(notebook, {**cursor, 'depth': {'rounds': []}})


def test_a_catchup_night_that_has_produced_nothing_does_not_deepen_at_the_closing_translation(notebook, monkeypatch):
    with catchup.scope(notebook, 3):
        cursor = cursor_of(notebook, [], catchup_night=3, closing=True)
        write_json(state_path(notebook, 'round.json'), cursor)
        assert not schedule._depth_early(notebook, cursor)
        write_json(state_path(notebook, 'round.json'), {**cursor, 'translated': 1})
        assert schedule._depth_early(notebook, cursor)


def test_the_nights_counts_carry_its_summaries_and_the_translations_its_bound_left(notebook, monkeypatch):
    with catchup.scope(notebook, 2):
        cursor = cursor_of(notebook, [], catchup_night=2, translated=5, translations_waiting=7)
        write_json(state_path(notebook, 'round.json'), cursor)
    for number in range(3):
        write_json(state_path(notebook, f'runs/run_summary{number}.json'),
                   {'id': f'run_summary{number}', 'phase': 'sessions-summary', 'catchup_night': 2,
                    'outcome': 'completed' if number else 'parked', 'started_at': service.now().isoformat()})
    counts = catchup._counts(notebook, 2)
    assert (counts['translated'], counts['translations_waiting'], counts['summarised']) == (5, 7, 2)


def test_the_nights_line_says_the_summaries_and_what_the_translation_bound_left(notebook, monkeypatch):
    row = {'mail': 0, 'sessions': 5, 'written': 6, 'decisions': 1, 'translated': 400, 'drafts': 0, 'changed': [],
           'parked': [], 'deepened': 3, 'deepen_reason': '', 'shares': {}, 'investigation_hold': '',
           'summarised': 15, 'translations_waiting': 25}

    def run(root, *, nights, progress, stage, say, cut_short):
        progress(1, row)
        return {'nights': [row], 'reason': '', 'failed': False, 'held': None, 'parked': [], 'candidates': '',
                'deepen_reason': '', **{name: row[name] for name in
                                        ('mail', 'sessions', 'written', 'decisions', 'translated', 'drafts', 'deepened')}}

    monkeypatch.setattr(catchup, 'run', run)
    result = CliRunner().invoke(app, ['rem', '--root', str(notebook), 'catchup'])
    assert result.exit_code == 0, result.output
    line = next(line for line in result.output.splitlines() if line.startswith('Night 1:'))
    assert ('400 pages translated (25 wait for the next round: limits.translations_per_round) · '
            '0 drafts prepared · 15 sessions summarised · ') in line


def test_status_says_how_many_pages_a_round_translates_at_most_while_pages_wait(notebook, monkeypatch):
    waiting_pages(monkeypatch)
    row = next(row for row in stages.status(notebook, read_config(notebook), []) if row['name'] == 'Translate')
    assert row['text'] == 'Translate: 12 page translations waiting; last ran never; a round translates up to 400'
    waiting_pages(monkeypatch, [])
    row = next(row for row in stages.status(notebook, read_config(notebook), []) if row['name'] == 'Translate')
    assert row['text'] == 'Translate: 0 page translations waiting; last ran never'


# One number for the week's investigation points (2026-11-17): status said "38 of 35 points
# used" under Investigate and "14.3 of 35 investigation points this week" under Budget. The
# first was the sentence a round saved before the points were counted without the
# round's own record; the second was counted when status was asked.

def budget(spent):
    return {'quota': {'used_percent': 40, 'resets_at': 4102444800, 'window_minutes': 10080, 'plan': 'pro'},
            'investigation_quota': {'spent_points': spent, 'budget_points': 35, 'floor_percent': 90}}


def held_queue(root):
    write_json(state_path(root, WAITING), {'night': '2026-09-08', 'jobs': [person('ivy'), person('wren')],
                                           'held': {**HELD, 'reason': HELD['reason'].replace('35 of 35', '38 of 35')}})


def investigate_row(root, spent):
    return next(row for row in stages.status(root, read_config(root), [], budget=budget(spent))
                if row['name'] == 'Investigate')


def test_status_does_not_repeat_a_hold_the_weeks_count_no_longer_supports(notebook):
    held_queue(notebook)
    row = investigate_row(notebook, 14.3)
    assert 'weekly budget' not in row['text'] and '38 of 35' not in row['text'] and 'budget_hold' not in row


def test_status_says_the_hold_with_the_number_its_budget_line_shows(notebook):
    held_queue(notebook)
    row = investigate_row(notebook, 36.5)
    assert '(36.5 of 35 points used; the Codex week resets' in row['budget_hold'] and '38 of 35' not in row['text']
    assert row['text'].endswith('; 2 pages wait')


def test_status_counts_the_weeks_points_once_for_the_hold_and_the_budget_line(notebook, monkeypatch):
    held_queue(notebook)
    calls = []
    counted = service._quota_status
    monkeypatch.setattr(service, '_quota_status', lambda config, logs: calls.append(1) or counted(config, logs))
    value = service.status(notebook, include_quota=True)
    assert len(calls) == 1 and 'investigation_quota' in value
    assert not any('budget_hold' in row for row in value['stages'])
