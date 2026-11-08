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


def test_prepared_person_primary_opens_review_without_navigating_to_today():
    result = run_js(['personPrimary'], r'''
      const r = {path: 'people/mara.md'}, draft = {status: 'prepared', id: 'fixture'};
      const threadDraft = () => draft, threadContact = () => null, href = r => '#r=' + r.path;
      const t = value => value, PEN_ICON = '', el = (tag, attrs) => ({...attrs, insertAdjacentHTML() {}});
      let prevented = false, reviewed = null;
      const openPersonDraft = (value, trigger) => { reviewed = [value.id, trigger.href]; };
      const button = personPrimary(r, {});
      button.onclick({preventDefault() {prevented = true;}});
      console.log(JSON.stringify({href: button.href, prevented, reviewed}));
    ''')
    assert result == {'href': '#r=people/mara.md&h=open-threads', 'prevented': True,
                      'reviewed': ['fixture', '#r=people/mara.md&h=open-threads']}


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


def test_person_no_reply_primary_offers_completion_instead_of_another_mail():
    result = run_js(['personPrimary'], r'''
      const entry = {t: {dir: 'mine'}}, r = {path: 'people/mara.md'};
      const threadDraft = () => ({status: 'no_reply'}), threadContact = () => ({address: 'mara@example.test'});
      const t = value => value, CHECK_ICON = '', el = (tag, attrs) => ({tag, ...attrs, insertAdjacentHTML() {}});
      let completed = false;
      const setDone = (item, state) => { completed = item === entry && state; };
      const button = personPrimary(r, entry);
      button.onclick();
      console.log(JSON.stringify({tag: button.tag, text: button.text, completed}));
    ''')
    assert result == {'tag': 'button', 'text': 'Mark done', 'completed': True}


def test_person_draft_review_closes_after_skip_and_restores_a_connected_control():
    result = run_js(['openPersonDraft'], r'''
      const events = {}, draft = {status: 'prepared'};
      let closed = false, removed = false, focused = '';
      const trigger = {isConnected: false, focus() {throw Error('stale trigger');}};
      const el = (tag, attrs, children) => tag === 'dialog' ? {
        addEventListener(name, callback) {events[name] = callback;},
        showModal() {}, close() {closed = true; events.close();}, remove() {removed = true;}
      } : {focus() {focused = 'close';}};
      const t = text => text, replyDraftCard = () => ({});
      const document = {body: {appendChild() {}}, querySelector() {return {focus() {focused = 'undo';}};}};
      openPersonDraft(draft, trigger);
      draft.status = 'skipped'; events.click();
      console.log(JSON.stringify({closed, removed, focused}));
    ''')
    assert result == {'closed': True, 'removed': True, 'focused': 'undo'}


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
