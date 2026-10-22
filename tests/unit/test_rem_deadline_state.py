"""An old timestamp cannot retire a recorded deadline or prove resolution."""
import json
import re
from datetime import date

import pytest

from connectonion.rem.census import _quiet
from connectonion.rem.reader import TEMPLATE
from test_rem_reader import _run_reader_js


@pytest.mark.parametrize('due', ['2026-10-15', '2026-10-20', '2026-10-23'])
def test_explicit_deadline_is_not_quiet_only_because_the_ask_is_old(due):
    assert not _quiet(f'The user owes Mara a draft since 2026-07-01; due {due}.', date(2026, 10, 20))


def test_reader_keeps_old_explicit_due_items_in_today_and_active_counts():
    page = TEMPLATE.read_text()
    names = ['writtenDatePattern', 'writtenDates', 'threads', 'listItems', 'isCalm', 'rawSection', 'todayEntries', 'threadCounts']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    result = _run_reader_js(functions + r'''
      const REM = {as_of:'2026-10-20'}, DAY_MS = 86400000, COMMENT = /<!--[\s\S]*?-->/g;
      const calendarDay = day => day, daysSince = () => 111, direction = () => 'mine';
      const r = {path:'people/mara.md', category:'people', text:'# Mara\n## Open threads\n' +
        '- You owe a draft since 2026-07-01; due 2026-10-15.\n' +
        '- You owe a review since 2026-07-01; due 2026-10-20.\n' +
        '- You owe a letter since 2026-07-01; due 2026-10-23.\n' +
        '- You owe an undated reply since 2026-07-01.\n'};
      const items = threads(r).items, threadEntries = () => items.map(t => ({r,t})), isDone = () => false;
      console.log(JSON.stringify({quiet:items.map(t=>t.quiet),counts:threadCounts(),today:todayEntries(threadEntries()).map(e=>e.t.due)}));
    ''')
    assert result['quiet'] == [False, False, False, True]
    assert result['counts'] == {'mine': 3, 'theirs': 0, 'other': 0, 'quiet': 1, 'open': 3}
    assert result['today'] == ['2026-10-15', '2026-10-20', '2026-10-23']


def test_person_synthesis_sent_to_runner_never_closes_a_thread_from_age_alone(tmp_path):
    from connectonion.rem import investigate as feature
    from connectonion.rem.files import Notebook
    from test_rem_investigate import _avery_page

    book, record, notes = Notebook(tmp_path), 'people/avery.md', []
    book.write(record, _avery_page(quotes=8, insight=3))

    def runner(notebook, items, config, stage):
        note = next(item['text'] for item in items if item['role'] == 'round')
        notes.append(note)
        if note.startswith('Round '):
            notebook.write(record, notebook.read(record) + '\nA new cited finding [1].\n')
            return {'changed': [record]}
        return {'changed': []}

    feature.run_rounds(runner, book, record, lambda text: {'role':'page','text':text}, [],
                       [[{'source':'gmail:one','text':'Please send the draft.'}]], {})
    final = next(note for note in notes if note.startswith('Final round'))
    assert 'quiet for 60 days moves to' not in final
    assert 'Age alone does not resolve' in final
    assert 'matching ask' in final
    assert 'past its due date stays' in final


def test_quiet_threads_remain_reviewable_without_claiming_everything_is_closed():
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0)
                          for name in ['waitingMore', 'quietThreads'])
    result = _run_reader_js(functions + r'''
      const el = (tag, attrs, children=[]) => ({tag,...attrs,children});
      const threadRow = () => ({});
      const notice = waitingMore({mine:0,theirs:0,quiet:2});
      const quiet = quietThreads([{t:{quiet:true},r:{}}], 1);
      console.log(JSON.stringify({notice, quiet}));
    ''')
    assert result['notice']['text'] == 'No active waiting items. 2 older threads remain to review.'
    assert result['quiet']['children'][1]['text'] == 'Grouped by their recorded dates, not verified as resolved.'


@pytest.mark.parametrize('due', ['15 October 2026', 'October 20, 2026', '23 Oct 2026'])
def test_written_deadlines_use_same_quiet_boundary_as_iso_dates(due):
    assert not _quiet(f'The user owes Mara a draft since 2026-07-01; due {due}.', date(2026, 10, 20))


@pytest.mark.parametrize('snapshot,since,due', [
    ('2026-10-20','2026-07-01','31 February 2026'),
    ('2026-10-20','2026-07-01','31 April 2026'),
    ('2024-03-01','2023-07-01','29 February 2024'),
    ('2024-01-01','2023-07-01','29 February'),
    ('2026-01-10','2025-07-01','December 20'),
])
def test_cli_reader_calendar_and_rollover_parity(snapshot, since, due):
    from connectonion.rem.census import _thread_dates
    line = f'You owe a draft since {since}; due {due}.'
    page = TEMPLATE.read_text()
    names = ['writtenDatePattern', 'writtenDates', 'threads', 'listItems', 'isCalm', 'rawSection']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    result = _run_reader_js(functions + '''
      const REM = {as_of:SNAPSHOT}, DAY_MS = 86400000, COMMENT = /<!--[\\s\\S]*?-->/g;
      const calendarDay = day => day, direction = () => 'mine';
      const daysSince = day => (Date.parse(REM.as_of)-Date.parse(day))/DAY_MS;
      console.log(JSON.stringify(threads({category:'people',text:'## Open threads\\n- '+LINE}).items[0]));
    '''.replace('SNAPSHOT', json.dumps(snapshot)).replace('LINE', json.dumps(line)))
    expected = _thread_dates(line, date.fromisoformat(snapshot))
    assert (result['since'], result['due']) == expected
    assert result['quiet'] == _quiet(line, date.fromisoformat(snapshot))
