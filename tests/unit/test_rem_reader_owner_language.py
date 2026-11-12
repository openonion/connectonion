"""The reader names the language of what it shows: the gist's title says what it is, rows not yet in the
reader's language carry the page header's 原文, and the top Today card is a draft that needs nothing from
the owner when one exists."""
import json
import re

from connectonion.rem.reader import TEMPLATE

from tests.unit.test_rem_reader import _run_reader_js


def functions(*names):
    page = TEMPLATE.read_text(encoding='utf-8')
    found = [re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names]
    return '\n'.join(found)


GIST = r'''
  UI.zh = {Gist: '要点', Original: '原文'};
  const nativeName = tag => ({en: 'English', zh: '中文'})[tag] || tag;
  const el = (tag, attrs) => ({tag, ...attrs});
  const out = {};
  for (const lang of ['zh', 'en']) {
    uiLanguage = lang;
    out[lang] = {english: gistTitle('Confirms the Tuesday call and sends the deck.'), chinese: gistTitle('确认周二通话，并发送资料。'),
                 englishRow: rowMark('Send Mara the signed data-sharing addendum')?.text || null,
                 chineseRow: rowMark('把签好的补充协议发给 Mara')?.text || null, shortRow: rowMark('OK')?.text || null};
  }
  console.log(JSON.stringify(out));
'''


def test_the_gist_title_names_its_language_and_rows_carry_the_original_mark():
    result = _run_reader_js(functions('textLanguage', 'gistTitle', 'originalMark', 'rowMark') + GIST)
    # Never 中文对照 over English: the title says it is the gist, and its language when not the reader's.
    assert result['zh'] == {'english': '要点 · English', 'chinese': '要点', 'englishRow': '原文', 'chineseRow': None, 'shortRow': None}
    # An English reader reads every page as written; nothing is marked (pages are never translated into English).
    assert result['en'] == {'english': 'Gist', 'chinese': 'Gist · 中文', 'englishRow': None, 'chineseRow': None, 'shortRow': None}
    assert '中文对照' not in TEMPLATE.read_text(encoding='utf-8')


def deck(groups):
    script = functions('deckOrder') + r'''
      let todayLead = null;
      const groups = ''' + json.dumps(groups) + r''';
      const groupStep = entries => entries[0];
      const threadDraft = entry => entry.draft;
      console.log(JSON.stringify(deckOrder(groups).map(group => group.r.path)));
    '''
    return _run_reader_js(script)


def group(path, step, body=None):
    return {'r': {'path': path}, 'entries': [{'step': step, 'entry': {'draft': {'body': body} if body else None}}]}


def test_among_ready_drafts_the_one_with_no_owner_slot_leads():
    slotted = group('people/ines.md', 'send', 'Hi Ines,\n\n【需要你：附件 / 链接 — date not agreed】')
    complete = group('people/mara.md', 'send', 'Hi Mara,\n\nThe addendum is attached.')
    first = group('people/tomas.md', 'reply')
    assert deck([first, slotted, complete]) == ['people/mara.md', 'people/tomas.md', 'people/ines.md']
    # Every ready draft slotted: the first of them still leads, as before.
    assert deck([first, slotted, group('people/rue.md', 'send', '【需要你：x — y】')]) == ['people/ines.md', 'people/rue.md', 'people/tomas.md']
    # Nothing ready to send: the deck keeps its order.
    assert deck([first, group('people/rue.md', 'done')]) == ['people/tomas.md', 'people/rue.md']
