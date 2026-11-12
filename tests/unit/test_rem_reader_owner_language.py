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
  const untranslated = {path: 'people/jordan-lee.md', translations: {}}, translated = {path: 'people/mara.md', translations: {zh: '# Mara'}};
  const regional = {path: 'people/li.md', translations: {'zh-TW': '# 李'}};
  const mark = (words, r) => rowMark(words, r)?.text || null;
  const out = {};
  for (const lang of ['zh', 'en']) {
    uiLanguage = lang;
    out[lang] = {english: gistTitle('Confirms the Tuesday call and sends the deck.'), chinese: gistTitle('确认周二通话，并发送资料。'),
                 mixed: gistTitle('跟进 Jordan Lee 的 Q3 pricing proposal，确认 API v2 的 deadline'),
                 englishRow: mark('Send Mara the signed data-sharing addendum', untranslated),
                 translatedRow: mark('Send Mara the signed data-sharing addendum', translated),
                 regionalRow: mark('Send Li the signed addendum', regional),
                 mixedRow: mark('跟进 Jordan Lee 的 Q3 pricing proposal (PR #2986, API v2)', untranslated),
                 shortRow: mark('OK', untranslated)};
  }
  console.log(JSON.stringify(out));
'''


def test_the_gist_title_names_its_language_and_rows_carry_the_original_mark():
    result = _run_reader_js(functions('textLanguage', 'gistTitle', 'originalMark', 'rowMark', 'hasChinese') + GIST)
    # Never 中文对照 over English: the title says it is the gist, and its language when not the reader's.
    # Names and codes inside Chinese words never make them English (review: a script count did).
    assert result['zh'] == {'english': '要点 · English', 'chinese': '要点', 'mixed': '要点',
                            # The mark is the page's: no current Chinese version and no Chinese words in the row.
                            'englishRow': '原文', 'translatedRow': None, 'regionalRow': None, 'mixedRow': None, 'shortRow': '原文'}
    # An English reader reads every page as written; nothing is marked (pages are never translated into English).
    assert result['en'] == {'english': 'Gist', 'chinese': 'Gist · 中文', 'mixed': 'Gist · 中文',
                            'englishRow': None, 'translatedRow': None, 'regionalRow': None, 'mixedRow': None, 'shortRow': None}
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
    # Any bracket replyDraftCard would hold Send for counts as a slot, not only 【需要你】.
    square = group('people/rue.md', 'send', 'Hi Rue,\n\nDue [date].')
    assert deck([first, square, complete]) == ['people/mara.md', 'people/tomas.md', 'people/rue.md']
    # Nothing ready to send: the deck keeps its order.
    assert deck([first, group('people/rue.md', 'done')]) == ['people/tomas.md', 'people/rue.md']


def test_the_page_header_mark_counts_a_regional_chinese_cache():
    result = _run_reader_js(functions('translationMark', 'originalMark', 'hasChinese') + r'''
      UI.zh = {Original: '原文'}; uiLanguage = 'zh';
      const el = (tag, attrs) => ({tag, ...attrs}), REM = {status: {worker: {enabled: true}}}, translationQueued = () => false;
      console.log(JSON.stringify([translationMark({translations: {'zh-TW': '# 李'}}), translationMark({translations: {}})?.text]));
    ''')
    assert result == [None, '原文']
