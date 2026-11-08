"""An old request date cannot retire a deadline or prove resolution."""
import re
from datetime import date

import pytest

from connectonion.rem.census import _quiet
from connectonion.rem.reader import TEMPLATE
from test_rem_reader import _run_reader_js


@pytest.mark.parametrize('since,due,quiet', [
    ('2026-07-01', '2026-10-15', False),
    ('2026-07-01', '2026-10-20', False),
    ('2026-07-01', '2026-10-23', False),
    ('2026-07-01', '', True),
    ('2026-08-21', '', False),  # Exactly 60 days remains active.
    ('2026-08-20', '', True),
])
def test_deadline_survives_age_only_quiet_grouping(since, due, quiet):
    text = f'The user owes Avery a draft since {since}' + (f'; due {due}.' if due else '.')
    assert _quiet(text, date(2026, 10, 20)) is quiet


def test_reader_keeps_old_deadlines_in_active_counts_and_today(tmp_path):
    from connectonion.rem.config import prepare
    from connectonion.rem.today import queue
    prepare(tmp_path)
    original = ('## Open threads\n'
                '- You owe a draft since 2026-07-01; due 2026-10-15.\n'
                '- You owe a review since 2026-07-01; due 2026-10-20.\n'
                '- You owe a letter since 2026-07-01; due 2026-10-23.\n'
                '- You owe a plan since 2026-07-01; due 2026-10-24.\n'
                '- You owe an undated reply since 2026-07-01.\n')
    # Python now chooses Today; the reader must retain its dates and done filter.
    rows = queue(tmp_path, records=[{'path': 'people/avery.md', 'text': '# Avery\n\n' + original, 'title': 'Avery'}], as_of=date(2026, 10, 20))
    page = TEMPLATE.read_text()
    names = ['writtenDatePattern', 'writtenDates', 'threads', 'listItems', 'isCalm',
             'rawSection', 'todayEntries', 'threadCounts']
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    import json
    result = _run_reader_js(functions + 'const queue = ' + json.dumps(rows) + ';\n' + r'''
      const REM = {as_of:'2026-10-20'}, DAY_MS = 86400000, COMMENT = /<!--[\s\S]*?-->/g;
      REM.today_queue = queue;
      const doneKey = entry => entry.r.path + '\n' + entry.t.originalText;
      const calendarDay = day => day, direction = () => 'mine';
      const daysSince = day => (Date.parse(REM.as_of) - Date.parse(day)) / DAY_MS;
      const original = '## Open threads\n' +
        '- You owe a draft since 2026-07-01; due 2026-10-15.\n' +
        '- You owe a review since 2026-07-01; due 2026-10-20.\n' +
        '- You owe a letter since 2026-07-01; due 2026-10-23.\n' +
        '- You owe a plan since 2026-07-01; due 2026-10-24.\n' +
        '- You owe an undated reply since 2026-07-01.\n';
      const r = {path:'people/avery.md', category:'people', original, shown:'zh',  // a page shown in translation keeps its English source
        text:original.replace('You owe a draft', 'Translated draft')};
      const items = threads(r).items, threadEntries = () => items.map(t => ({r,t}));
      const isDone = entry => entry.t.due === '2026-10-20';
      console.log(JSON.stringify({items, counts:threadCounts(), today:todayEntries(threadEntries()).map(e=>e.t.due)}));
    ''')
    assert [item['quiet'] for item in result['items']] == [False, False, False, False, True]
    assert result['items'][0]['text'].startswith('Translated draft')
    assert result['items'][0]['originalText'].startswith('You owe a draft')
    assert result['counts'] == {'mine': 3, 'theirs': 0, 'other': 0, 'quiet': 1, 'open': 3}
    assert result['today'] == ['2026-10-15', '2026-10-23']


def test_person_synthesis_dispatched_to_runner_requires_matching_resolution(tmp_path):
    from connectonion.rem import investigate
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

    investigate.run_rounds(runner, book, record, lambda text: {'role': 'page', 'text': text}, [],
                           [[{'source': 'gmail:one', 'text': 'Please send the draft.'}]], {})
    final = next(note for note in notes if note.startswith('Final round'))
    assert 'quiet for 60 days moves to' not in final
    assert 'Age alone does not resolve' in final
    assert 'matching ask' in final
    assert 'a promise past its due date stays' in final
