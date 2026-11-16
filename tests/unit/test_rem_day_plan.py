"""Saved, deterministic days: no provider or model is involved (#3058)."""
from datetime import datetime, timezone

import pytest

from connectonion.rem.config import default_config, prepare, read_config
from connectonion.rem.files import read_json, state_path, write_json

NOW = datetime(2026, 11, 16, 0, tzinfo=timezone.utc)


def item(n=0, **extra):
    return dict(key=str(n), rank=n, record='people/mara.md', title='Mara',
                text=f'Send draft {n} [1]', dir='mine', since='2026-11-14', due='',
                closed=False, quiet=False, reply={}, **extra)


def event(start='10:00', end='11:00', **extra):
    return dict(title='Meeting', start=f'2026-11-16T{start}:00+00:00',
                end=f'2026-11-16T{end}:00+00:00', all_day=False,
                location='12 Harbour Street\nSydney', link='https://calendar.test/event',
                people=['people/mara.md'], **extra)


def plan(events=(), items=(), config=None, moment=NOW, read=True):
    from connectonion.rem.day_plan import build
    if config is None:
        config = default_config()
        config['schedule']['timezone'] = 'UTC'
    config['schedule']['timezone'] = config['schedule'].get('timezone') or 'UTC'
    return build({'read': [{'name': 'Calendar'}] if read else [], 'events': list(events)},
                 list(items), config, moment)


def proposals(day):
    return [row for row in day['items'] if row['kind'] == 'proposal']


def test_day_plan_events_and_proposals_order_longest_gap_and_rank():
    saved = plan([event('16:00', '17:00'), event()], [item(4), item(1), item(2)])
    day = saved['days'][0]
    assert day['date'] == '2026-11-16'
    assert [(r['kind'], r['time']) for r in day['items']] == [
        ('event', '10:00'), ('proposal', '11:00'), ('proposal', '11:30'),
        ('proposal', '12:00'), ('event', '16:00')]
    assert [r['key'] for r in proposals(day)] == ['1', '2', '4']
    assert day['items'][0]['people'] == ['people/mara.md']
    assert day['items'][0]['link'] == 'https://calendar.test/event'
    assert day['items'][0]['location'] == '12 Harbour Street\nSydney'


def test_day_plan_half_hour_boundaries_overlap_and_does_not_fit():
    config = default_config()
    config['schedule']['timezone'] = 'UTC'
    config['schedule']['working_hours'] = {'start': '09:10', 'end': '11:00'}
    day = plan([event('10:00', '10:40'), event('10:20', '11:00')],
               [item(0), item(1)], config)['days'][0]
    rows = proposals(day)
    assert rows[0]['time'] == '09:30' and rows[0]['end_time'] == '10:00'
    assert rows[1]['time'] == '' and rows[1]['placement'] == 'no free time today'


def test_day_plan_maximum_five_open_mine_in_existing_order_and_word_reasons():
    rows = [item(i) for i in range(9)]
    rows[0]['closed'] = True
    rows[1]['quiet'] = True
    rows[2]['dir'] = 'theirs'
    rows[3]['due'] = '2026-11-16'
    rows[4]['due'] = '2026-11-15'
    rows[5]['reply'] = {'last_word_yours': True, 'promise': 'I will send it.'}
    picked = proposals(plan(items=rows)['days'][0])
    assert [r['key'] for r in picked] == ['3', '4', '5', '6', '7']
    assert 'due today' in picked[0]['reason']
    assert 'late since 2026-11-15' in picked[1]['reason']
    assert 'promised to Mara' in picked[2]['reason']
    assert 'Mara waiting since 2026-11-14' in picked[3]['reason']
    assert all(r['record'] == 'people/mara.md' for r in picked)


@pytest.mark.parametrize('location,missing', [
    ('Harbour Cafe', True), ('Office', True), ('悉尼咖啡馆', True),
    ('12 Harbour', False), ('Harbour Street', False), ('Kings Rd', False),
    ('中山路', False), ('', False), ('A very long venue name with seven words', False),
])
def test_day_plan_simple_address_rule_preserves_exact_calendar_text(location, missing):
    row = event()
    row['location'] = location
    shown = plan([row])['days'][0]['items'][0]
    assert shown['location'] == location and shown['address_missing'] is missing


def test_day_plan_zone_tomorrow_and_exclusive_all_day_end():
    config = default_config()
    config['schedule']['timezone'] = 'Australia/Sydney'
    all_day = event()
    all_day.update(start='2026-11-16', end='2026-11-17', all_day=True, title='Away')
    next_day = event()
    next_day.update(start='2026-11-16T22:00:00Z', end='2026-11-16T23:00:00Z', title='Tomorrow visit')
    saved = plan([next_day, all_day], [item()], config, datetime(2026, 11, 15, 23, tzinfo=timezone.utc))
    assert saved['timezone'] == 'Australia/Sydney'
    assert saved['days'][0]['date'] == '2026-11-16'
    assert proposals(saved['days'][0])[0]['placement'] == 'no free time today'
    tomorrow = saved['days'][1]
    assert tomorrow['date'] == '2026-11-17'
    assert [(r['title'], r['time']) for r in tomorrow['items'] if r['kind'] == 'event'] == [('Tomorrow visit', '09:00')]
    assert proposals(tomorrow)[0]['time'] == '10:00'


def test_day_plan_timed_event_crossing_midnight_blocks_both_days():
    row = event()
    row.update(start='2026-11-15T23:00:00Z', end='2026-11-17T10:00:00Z')
    days = plan([row], [item()])['days']
    assert proposals(days[0])[0]['placement'] == 'no free time today'
    assert proposals(days[1])[0]['time'] == '10:00'


@pytest.mark.parametrize('calendar', [None, {'read': [], 'events': []}])
def test_day_plan_no_calendar_read_keeps_proposals_without_times(calendar):
    from connectonion.rem.day_plan import build, text
    saved = build(calendar, [item()], default_config(), NOW)
    assert saved['calendar_read'] is False
    row = proposals(saved['days'][0])[0]
    assert row['time'] == '' and row['placement'] == ''
    assert 'No calendar has been read yet.' in text(saved, '2026-11-16')
    assert 'Mara waiting since 2026-11-14' in text(saved, '2026-11-16')


def test_day_plan_config_optional_working_hours_roundtrip_and_validation(tmp_path):
    import yaml
    from connectonion.rem.config import validate
    from connectonion.rem.files import RemError
    prepare(tmp_path)
    config = read_config(tmp_path)
    config['schedule']['working_hours'] = {'start': '08:30', 'end': '16:00'}
    (tmp_path / 'config.yaml').write_text(yaml.safe_dump(config))
    assert read_config(tmp_path)['schedule']['working_hours'] == config['schedule']['working_hours']
    for bad in ({'start': '18:00', 'end': '09:00'}, {'start': '25:00', 'end': '18:00'}):
        config['schedule']['working_hours'] = bad
        with pytest.raises(RemError, match='working_hours'):
            validate(config)


def test_day_plan_saved_reader_and_status_are_offline_and_shared_reader_omits_it(tmp_path, monkeypatch):
    from connectonion.rem import calendar, day_plan, service
    from connectonion.rem.reader import snapshot
    prepare(tmp_path)
    monkeypatch.setattr(service, 'now', lambda: NOW)
    saved = plan([event()], [item()])
    write_json(state_path(tmp_path, 'day-plan.json'), saved)
    monkeypatch.setattr(calendar, 'calendar_events', lambda *a: pytest.fail('network'))
    monkeypatch.setattr(day_plan, 'build', lambda *a: pytest.fail('recomputed saved plan'))
    assert snapshot(tmp_path, local=True)['day_plan'] == saved
    assert snapshot(tmp_path, local=False)['day_plan'] is None
    assert service.status(tmp_path)['day_plan']['text'] == day_plan.text(saved, '2026-11-16').replace('\n', '; ')


def test_day_plan_owner_question_is_not_a_promise_and_project_does_not_wait():
    rows = [item(0), item(1)]
    rows[0]['reply'] = {'last_word_yours': True, 'promise': 'Which dates work for you?'}
    rows[1].update(record='projects/harbour.md', title='Harbour')
    chosen = proposals(plan(items=rows)['days'][0])
    assert 'promised to' not in chosen[0]['reason']
    assert 'Harbour waiting' not in chosen[1]['reason']
    assert 'open item on Harbour' in chosen[1]['reason']


def test_day_plan_retained_calendar_failure_is_said_with_last_read_date():
    from connectonion.rem.day_plan import build, text
    calendar = {'read': [], 'errors': [{'name': 'Google Calendar', 'reason': 'login expired',
        'read_at': '2026-11-14T04:00:00Z', 'at': NOW.isoformat()}], 'events': [event()]}
    saved = build(calendar, [item()], default_config(), NOW)
    assert saved['calendar_errors'] == calendar['errors']
    words = text(saved, saved['days'][0]['date'])
    assert 'login expired' in words and 'events last read 2026-11-14' in words


def test_day_plan_upgrade_fallback_reads_only_saved_calendar(tmp_path, monkeypatch):
    from connectonion.rem import calendar, day_plan, service
    prepare(tmp_path)
    monkeypatch.setattr(service, 'now', lambda: NOW)
    monkeypatch.setattr(calendar, 'calendar_events', lambda *a: pytest.fail('network'))
    write_json(state_path(tmp_path, 'calendar.json'), {'read_at': {'google': NOW.isoformat()},
        'saved_at': NOW.isoformat(), 'events': [event()], 'errors': {}})
    shown = day_plan.read(tmp_path, items=[item()])
    assert shown['calendar_read'] is True
    assert shown['not_saved'] is True
    assert 'No day plan has been saved yet.' in day_plan.text(shown, shown['days'][0]['date'])
    assert 'No calendar has been read yet.' not in day_plan.text(shown, shown['days'][0]['date'])
    assert all(row['time'] == '' for day in shown['days'] for row in day['items'])
    assert not state_path(tmp_path, 'day-plan.json').exists()


def test_day_plan_skips_stale_dated_promises_before_taking_five():
    rows = [item(n) for n in range(9)]
    for row in rows[:5]:
        row.update(due='2026-08-01', since='2026-08-01')
    rows[5]['due'] = '2026-08-01'  # recent correspondence keeps an old deadline active
    rows[6]['due'] = '2026-11-15'
    assert [r['key'] for r in proposals(plan(items=rows)['days'][0])] == ['5', '6', '7', '8']


def test_day_plan_project_promise_never_names_project_as_person():
    row = item()
    row.update(record='projects/harbour.md', title='Harbour',
               reply={'last_word_yours': True, 'promise': 'I will send it.'})
    chosen = proposals(plan(items=[row])['days'][0])[0]
    assert chosen['reason'] == 'open item on Harbour'


def _real_shaped_events():
    """The shapes a saved calendar.json really holds: offsets, date-only all-day rows, empty titles, a week-long timed row."""
    row = lambda start, end, **extra: dict(id=start + end, title='', all_day=False, start=start, end=end, location='',
                                           link='https://calendar.test/e', attendees=[], calendar='google', **extra)
    return [row('2026-11-15T09:00:00+11:00', '2026-11-21T17:00:00+11:00') | {'title': 'Harbour sprint'},
            row('2026-11-16', '2026-11-17') | {'all_day': True},
            row('2026-11-16T14:00:00+11:00', '2026-11-16T15:00:00+11:00') | {'calendar': 'microsoft'},
            row('2026-11-17T22:00:00+11:00', '2026-11-18T01:00:00+11:00') | {'title': 'Late call', 'location': 'Harbour Cafe'},
            row('2026-11-21T08:00:00+11:00', '2026-11-21T08:00:00+11:00') | {'title': 'Reminder'}]


def test_day_plan_real_shaped_saved_calendar_reaches_the_owner_reader_and_not_a_shared_page(tmp_path, monkeypatch):
    """A page rendered without local=True is the shared one: it carries no meeting and no plan, by design."""
    from connectonion.rem import calendar, day_plan, service
    from connectonion.rem.reader import render, snapshot
    prepare(tmp_path)
    config = read_config(tmp_path)
    config['schedule']['timezone'] = 'Australia/Sydney'
    import yaml
    (tmp_path / 'config.yaml').write_text(yaml.safe_dump(config))
    moment = datetime(2026, 11, 16, 1, 6, tzinfo=timezone.utc)
    monkeypatch.setattr(service, 'now', lambda: moment)
    monkeypatch.setattr(calendar, 'calendar_events', lambda *a: pytest.fail('network'))
    stamp = moment.isoformat(timespec='seconds')
    write_json(state_path(tmp_path, 'calendar.json'), {'saved_at': stamp, 'days': 21, 'errors': {}, 'capped': [],
               'read_at': {'google': stamp, 'microsoft': stamp}, 'events': _real_shaped_events()})
    day_plan.save(tmp_path, moment)
    own = snapshot(tmp_path, local=True)
    assert len(own['calendar']['events']) == 5 and own['day_plan']['timezone'] == 'Australia/Sydney'
    today, tomorrow = own['day_plan']['days']
    assert today['date'] == '2026-11-16'
    # A week-long timed event covers this whole day: it is all day here, never "00:00–00:00".
    assert [(r['title'], r['all_day'], r['time'], r['end_time']) for r in today['items']] == [
        ('Harbour sprint', True, '', ''), ('', True, '', ''), ('', False, '14:00', '15:00')]
    late = next(r for r in tomorrow['items'] if r['title'] == 'Late call')
    assert (late['time'], late['end_time'], late['address_missing']) == ('22:00', '24:00', True)
    words = day_plan.text(own['day_plan'], '2026-11-16')
    assert 'All day Harbour sprint' in words and '00:00–00:00' not in words
    assert '14:00–15:00 No title' in words and 'All day No title' in words
    assert 'Harbour Cafe — address not in the calendar event' in words
    assert '"day_plan": null' not in render(tmp_path, live=False, local=True)
    assert '"day_plan": null' not in render(tmp_path, live=True, local=True)
    shared = snapshot(tmp_path)
    assert shared['calendar'] is None and shared['day_plan'] is None and shared['shared'] is True
