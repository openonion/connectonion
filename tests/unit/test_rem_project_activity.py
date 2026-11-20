"""A project's activity strip counts what the notebook dates, by week, on one scale (#3096).

The owner: «GitHub's contribution record shows activity clearly; here I cannot see it. Why is the most
frequent activity not at the top, as in People?» These hold the counting and the order; the drawing is
tested in the browser (tests/e2e/cli/test_rem_projects_activity_browser.py). All data here is invented.
"""

from datetime import date, timezone
from zoneinfo import ZoneInfo

from connectonion.rem.project_activity import (attach, dated, level, local_day, order, quiet, scale, week_of,
                                               weekly)

SYDNEY = ZoneInfo('Australia/Sydney')
TODAY = date(2026, 11, 17)  # a Tuesday


def _message(stamp):
    return {'timestamp': stamp, 'source': 'codex:abc:1', 'text': 'invented'}


def test_a_week_starts_on_monday_and_a_stamp_is_read_in_the_notebooks_zone():
    assert week_of('2026-11-17') == '2026-11-16'
    assert week_of('2026-11-16') == '2026-11-16' and week_of('2026-11-22') == '2026-11-16'
    assert week_of('2026-11-23') == '2026-11-23'
    # 20:30 UTC on Sunday is already Monday morning in Sydney: it belongs to the new week.
    assert local_day('2026-11-15T20:30:00+00:00', SYDNEY) == '2026-11-16'
    assert local_day('2026-11-15T20:30:00+00:00', timezone.utc) == '2026-11-15'
    assert local_day('2026-11-15', SYDNEY) == '2026-11-15'  # a written day has no zone


def test_weeks_are_buckets_of_days_and_every_kind_adds_up():
    assert weekly(['2026-11-02', '2026-11-03', '2026-11-08', '2026-11-09']) == {'2026-11-02': 3, '2026-11-09': 1}
    assert weekly([]) == {}


def test_a_session_counts_once_only_when_none_of_its_messages_were_kept_that_day():
    days = dated([_message('2026-11-03T01:00:00+00:00'), _message('2026-11-03T02:00:00+00:00')],
                 ['2026-11-03', '2026-11-05', '2026-11-05'], ['2026-10-01T09:00:00+00:00', ''], '', timezone.utc)
    assert days == {'messages': ['2026-11-03', '2026-11-03'], 'sessions': ['2026-11-05', '2026-11-05'],
                    'mail': ['2026-10-01'], 'page': []}


def test_the_pages_last_activity_counts_only_on_a_day_nothing_else_was_counted():
    kept = [_message('2026-11-03T01:00:00+00:00')]
    assert dated(kept, [], [], '2026-11-03', timezone.utc)['page'] == []
    assert dated(kept, [], [], '2026-11-09', timezone.utc)['page'] == ['2026-11-09']
    assert dated([], [], [], '2026-11-09T23:30:00+00:00', SYDNEY)['page'] == ['2026-11-10']


def test_one_scale_for_every_project_in_five_steps():
    rows = [{'2026-11-02': 1, '2026-11-09': 2}, {'2026-11-02': 8, '2026-11-09': 40}, {'2026-10-05': 3, '2026-10-12': 5}]
    bounds = scale(rows)
    assert len(bounds) == 4 and bounds[0] == 1 and bounds == sorted(set(bounds))
    assert [level(n, bounds) for n in (0, 1, 40)] == [0, 1, 4]
    # The same count is the same step in every row: a busy project does not dim a quiet one's scale.
    assert level(3, bounds) == level(3, scale(rows))
    assert scale([]) == [1, 2, 3, 4] and scale([{'2026-11-02': 1}]) == [1, 2, 3, 4]


def test_quiet_is_thirty_days_without_dated_activity():
    assert not quiet('2026-10-18', TODAY) and quiet('2026-10-17', TODAY)
    assert quiet('', TODAY)


def test_order_is_the_most_recently_active_first_and_the_busier_first_within_a_week():
    rows = [{'title': 'Steady', 'last': '2026-11-10', 'recent': 40},
            {'title': 'New today', 'last': '2026-11-17', 'recent': 1},
            {'title': 'Busy last week', 'last': '2026-11-12', 'recent': 90},
            {'title': 'alpha tie', 'last': '2026-11-17', 'recent': 1},
            {'title': 'Never', 'last': '', 'recent': 0},
            {'title': 'Summer', 'last': '2026-08-20', 'recent': 0}]
    assert [row['title'] for row in order(rows)] == ['alpha tie', 'New today', 'Busy last week', 'Steady', 'Summer', 'Never']


def _project(slug, **extra):
    return {'path': f'projects/{slug}.md', 'category': 'projects', 'title': slug.title(), 'text': '# x\n', **extra}


def test_attach_gives_each_project_its_weeks_and_the_page_one_scale_and_one_order():
    records = [_project('kiln'), _project('orchard'), _project('attic'),
               {'path': 'sessions/2026-11-12-glaze.md', 'category': 'sessions', 'title': 'Glaze',
                'session_project': 'projects/orchard.md', 'session_date': '2026-11-12'},
               {'path': 'people/mara.md', 'category': 'people', 'title': 'Mara', 'text': ''}]
    kept = {'projects/kiln.md': [_message('2026-11-16T03:00:00+00:00')] * 3 + [_message('2026-09-01T03:00:00+00:00')]}
    summary = attach(records, lambda path: kept.get(path, []), {}, TODAY, timezone.utc)
    kiln, orchard, attic = records[:3]
    assert kiln['activity']['weeks'] == {'2026-08-31': 1, '2026-11-16': 3}
    assert kiln['activity']['kinds'] == {'messages': 4, 'sessions': 0, 'mail': 0, 'page': 0}
    assert (kiln['activity']['first'], kiln['activity']['last'], kiln['activity']['recent']) == ('2026-09-01', '2026-11-16', 4)
    assert orchard['activity']['weeks'] == {'2026-11-09': 1} and orchard['activity']['kinds']['sessions'] == 1
    assert attic['activity'] == {'weeks': {}, 'kinds': {'messages': 0, 'sessions': 0, 'mail': 0, 'page': 0}, 'first': '',
                                 'last': '', 'recent': 0, 'rank': 2, 'quiet': True}
    assert [r['activity']['rank'] for r in records[:3]] == [0, 1, 2]
    assert not kiln['activity']['quiet'] and not orchard['activity']['quiet']
    assert 'activity' not in records[4]
    assert summary == {'scale': scale([kiln['activity']['weeks'], orchard['activity']['weeks']]),
                       'kinds': {'messages': 4, 'sessions': 1, 'mail': 0, 'page': 0}, 'first': '2026-08-31',
                       'this_week': '2026-11-16', 'quiet_days': 30, 'recent_weeks': 12}


def test_recent_counts_the_last_twelve_weeks_only_and_cited_mail_is_dated_by_its_context():
    text = '# Kiln\n\n## Sources\n- [1] gmail:m1\n- [2] gmail:m2\n- [3] codex:abc:4\n'
    records = [_project('kiln', text=text)]
    contexts = {'gmail:m1': {'time': '2026-11-02T05:00:00+00:00'}, 'gmail:m2': {},
                'codex:abc:4': {'time': '2026-11-03T05:00:00+00:00'}}
    kept = {'projects/kiln.md': [_message('2026-06-01T03:00:00+00:00')] * 5}
    attach(records, lambda path: kept.get(path, []), contexts, TODAY, timezone.utc)
    activity = records[0]['activity']
    assert activity['kinds'] == {'messages': 5, 'sessions': 0, 'mail': 1, 'page': 0}  # an undated mail and a session source add nothing
    assert activity['recent'] == 1 and activity['weeks'] == {'2026-06-01': 5, '2026-11-02': 1}
