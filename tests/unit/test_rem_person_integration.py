"""Integration regressions for the merged People presentation."""

import json
import re
import shutil
import subprocess

import pytest

from connectonion.rem.reader import TEMPLATE


def run_js(names, script):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node runs the reader JavaScript')
    page = TEMPLATE.read_text()
    functions = '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)
    result = subprocess.run([node], input=functions + '\n' + script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('text', [
    'Mara gives examples, e.g.support letters. Send the draft: include details, please. Third sentence.',
    'Version 3.5 uses example.test. Next sentence. Third sentence.',
    '前文。需要草稿：保留说明，及细节！第三句。',
    '公开介绍。秘密信息[personal]。公开结尾。',
])
def test_reader_person_lead_keeps_english_punctuation_and_private_passages(text):
    """The full memory now retains the complete intro, including its privacy markup."""
    result = run_js(['markdown', 'inline', 'privatePassages'], r'''
      const UNKNOWN_TEXT = /^Unknown$/, uiLanguage = 'en';
      const esc = value => value, youify = value => value;
      const tetherCitations = value => value, uncertainCitations = value => value, quoteSpans = value => value;
      console.log(JSON.stringify(markdown(''' + json.dumps(text) + r''', 'people/mara.md')));
    ''')
    plain = re.sub(r'<[^>]+>', '', result)
    assert plain == text.replace('[personal]', 'personal')
    if '[personal]' in text:
        assert '<span class="private" data-level="personal">秘密信息' in result
        assert result.startswith('<p>公开介绍。')
        assert '公开结尾。' in result


@pytest.mark.parametrize('language', ['en', 'zh'])
@pytest.mark.parametrize('history', ['active', 'old', 'none'])
def test_person_contact_metric_is_a_true_readable_sentence(language, history):
    page = TEMPLATE.read_text()
    ui = page[page.index('const UI = {'):page.index('function t(')]
    script = ui + '\nlet uiLanguage = ' + json.dumps(language) + ';\n'
    script += r'''
      const REM = {as_of: '2026-11-08T12:00:00Z'};
      const uiLocale = () => uiLanguage === 'zh' ? 'zh-CN' : 'en-US';
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children});
      const facts = () => ({mails: 9, first: '2025-01-02', last: ''});
      const history = ''' + json.dumps(history) + r''';
      const last_mail = history === 'none' ? '' : history === 'old' ? '2025-01-02T12:00:00Z' : '2026-11-07T12:00:00Z';
      const weekly_messages = history === 'active' ? [...Array(48).fill(1), 0, 1, 2, 3] : Array(52).fill(0);
      const stats = personStats({title: 'Mara Ostrowski', index: {relationship: {last_mail, weekly_messages}}});
      console.log(JSON.stringify(stats.children.map(cell => [cell.children[0].text, cell.children[1]])));
    '''
    result = run_js(['personStats', 'replyDuration', 'firstName', 'fmtDate', 'calendarDay', 't'], script)
    assert result[0] == (['54', 'mails this year' if language == 'en' else '封邮件往来 · 一年内']
                          if history == 'active' else ['9', 'mails exchanged' if language == 'en' else '封邮件往来'])
    assert 'undefined' not in json.dumps(result) and 'null' not in json.dumps(result)


@pytest.mark.parametrize('company,label', [
    ('[[orgs/fernhill]]', 'Fernhill Labs'),
    ('[[orgs/fernhill.md|Fernhill 中文]]', 'Fernhill 中文'),
    ('[页面上的名称](../orgs/fernhill.md)', '页面上的名称'),
    ('', 'Fernhill Labs'),
])
def test_person_organisation_resolves_new_wikilinks_and_keeps_page_written_labels(company, label):
    result = run_js(['personOrg'], r'''
      const facts = () => ({company: ''' + json.dumps(company) + r'''});
      const plainLine = text => text, knownValue = Boolean;
      const org = {path: 'orgs/fernhill.md', title: 'Fernhill Labs'};
      const byPath = path => path === org.path ? org : null;
      console.log(JSON.stringify(personOrg({organisations: [org.path]})));
    ''')
    assert result['org']['path'] == 'orgs/fernhill.md'
    assert result['name'] == label


def test_person_quotes_skip_mail_that_only_a_private_passage_cites():
    """The person ledger whose source marks this guarded is gone (D-30); its quotes inherit the rule:
    a mail cited only by a [personal] passage is never quoted, and greetings and reactions are not their words."""
    result = run_js(['personQuotes', 'privatePassages', 'unlabelled'], r'''
      const r = {title: 'Mara Ostrowski', path: 'people/mara.md',
        text: 'Public ask [2]. Private ask [3][personal]. Reacted [4].\n\n## Sources\n- [2] gmail:a\n- [3] gmail:b\n- [4] gmail:c\n'};
      const REM = {source_context: {'gmail:a': {excerpt: 'Hi Avery,\nThe renewal can include a fourth seat.', sender: 'Mara', time: '2026-10-01'},
        'gmail:b': {excerpt: 'My private news, please keep it to yourself.', sender: 'Mara', time: '2026-10-02'},
        'gmail:c': {excerpt: 'Mara reacted to your message: Hi Mara, thanks!', sender: 'Mara', time: '2026-10-03'}}};
      const sourceList = () => [2, 3, 4].map(n => ({n: String(n), text: 'gmail:' + 'abc'[n - 2]}));
      const sourceId = text => text, facts = () => ({email: ''}), firstName = () => 'Mara', t = text => text;
      const fmtDate = day => day, calendarDay = day => day, inline = text => text;
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: [].concat(children).filter(Boolean)});
      console.log(JSON.stringify(personQuotes(r).children[1].children.map(li => li.children[1].text)));
    ''')
    assert result == ['The renewal can include a fourth seat.']


def test_owed_parts_drop_a_rest_that_is_only_punctuation_after_date_clutter():
    """"… before internal beta [11] — open as of 2026-11-03." left a lone "." on its own line."""
    result = run_js(['owedParts'], r'''
      const unlabelled = text => text, plainLine = text => text, capFirst = text => text;
      const withoutDateClutter = text => text.replace(/open as of \d{4}-\d{2}-\d{2}/, '').trim();
      console.log(JSON.stringify(owedParts({t: {text: 'Fern asked you to check the plan before beta [11] — open as of 2026-11-03.'}})));
    ''')
    assert result['rest'] == ''
    assert result['head'] == 'Fern asked you to check the plan before beta [11]'
