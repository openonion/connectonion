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
    result = run_js(['personQuotes', 'quoteRow', 'showAll', 'publicOnlyCites', 'saidWords', 'hasPrivacy', 'saidToYou', 'isAutoReply', 'privatePassages', 'unlabelled'], r'''
      const r = {title: 'Mara Ostrowski', path: 'people/mara.md',
        text: 'Public ask [2]. Private ask [3][personal]. Reacted [4].\n\n## Sources\n- [2] gmail:a\n- [3] gmail:b\n- [4] gmail:c\n'};
      const to = {to: ['avery@lin.example'], cc: []};
      const REM = {source_context: {'gmail:a': {excerpt: 'Hi Avery,\nThe renewal can include a fourth seat.', sender: 'Mara', time: '2026-10-01', participants: to},
        'gmail:b': {excerpt: 'My private news, please keep it to yourself.', sender: 'Mara', time: '2026-10-02', participants: to},
        'gmail:c': {excerpt: 'Mara reacted to your message: Hi Mara, thanks!', sender: 'Mara', time: '2026-10-03', participants: to}}};
      const ownerAddresses = () => ['avery@lin.example'];
      const sourceList = () => [2, 3, 4].map(n => ({n: String(n), text: 'gmail:' + 'abc'[n - 2]}));
      const sourceId = text => text, facts = () => ({email: ''}), firstName = () => 'Mara', t = text => text;
      const fmtDate = day => day, calendarDay = day => day, inline = text => text;
      const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: [].concat(children).filter(Boolean)});
      console.log(JSON.stringify(personQuotes(r).children[1].children.map(li => li.children[1].text)));
    ''')
    assert result == ['The renewal can include a fourth seat.']


def test_person_quotes_keep_only_mail_said_to_the_owner_personally():
    """An auto-reply, a bulk send to a list, a Bcc and a thirty-person announcement are hers but not said to him."""
    result = run_js(['saidToYou', 'isAutoReply'], r'''
      const owner = ['avery@lin.example'], to = list => ({to: list, cc: []});
      const mail = (subject, excerpt, participants) => ({subject, excerpt, participants});
      const crowd = Array.from({length: 30}, (_, i) => 'member' + i + '@fieldwork.example');
      console.log(JSON.stringify([
        mail('Renewal', 'The renewal can include a fourth seat.', to(['Avery Lin <avery@lin.example>'])),
        mail('Renewal', 'Copying the team so they know.', {to: ['kai@fernhill.example'], cc: ['avery@lin.example']}),
        mail('Automatic reply: Renewal', 'I will be back on Monday.', to(['avery@lin.example'])),
        mail('Re: Renewal', 'Thanks for your email! As a coordinator I am often away from my desk; I will respond soon.', to(['avery@lin.example'])),
        mail('Quick reminder: shared kitchen', 'Please keep the kitchen clean.', to(['members@fieldwork.example'])),
        mail('Calling founders', 'Workshop places are open.', to(crowd.concat(['avery@lin.example']))),
        mail('Renewal', 'No recipients were kept for this one.', {}),
      ].map(c => saidToYou(c, owner))));
    ''')
    assert result == [True, True, False, False, False, False, False]


QUOTE_HARNESS = r'''
  const to = {to: ['avery@lin.example'], cc: []};
  const sourceId = text => text, facts = () => ({email: ''}), firstName = () => 'Mara', t = text => text;
  const fmtDate = day => day, calendarDay = day => day, inline = text => text;
  const el = (tag, attrs = {}, children = []) => ({tag, ...attrs, children: [].concat(children).filter(Boolean)});
  const sourceList = () => [{n: '3', text: 'gmail:b'}];
  const ownerAddresses = () => OWNER;
'''
QUOTE_NAMES = ['personQuotes', 'quoteRow', 'showAll', 'publicOnlyCites', 'saidWords', 'saidToYou', 'isAutoReply', 'privatePassages', 'unlabelled', 'hasPrivacy']


def _quotes(text, excerpt, participants="to", owner="['avery@lin.example']"):
    return run_js(QUOTE_NAMES, QUOTE_HARNESS.replace('OWNER', owner) + f'''
      const r = {{title: 'Mara Ostrowski', path: 'people/mara.md', text: {text!r}}};
      const REM = {{source_context: {{'gmail:b': {{excerpt: {excerpt!r}, sender: 'Mara', time: '2026-10-02', participants: {participants}}}}}}};
      const out = personQuotes(r);
      console.log(JSON.stringify(out ? out.children[1].children.map(li => li.children[1].text) : []));
    ''')


def test_a_mail_any_private_passage_cites_is_never_quoted():
    """A public sentence citing the same mail does not make it public: the private one decides."""
    sources = '\n\n## Sources\n- [3] gmail:b\n'
    excerpt = 'The clinic round failed again, so I need to move our call.'
    assert _quotes('Moved the call [3]. Going through IVF [personal] [3].' + sources, excerpt) == []
    assert _quotes('Moved the call [3].' + sources, excerpt) == [excerpt]


def test_quotes_need_known_owner_addresses_and_an_unlabelled_excerpt():
    sources = '\n\n## Sources\n- [3] gmail:b\n'
    plain = 'The renewal can include a fourth seat.'
    assert _quotes('Renewal [3].' + sources, plain, owner='[]') == [], "no owner addresses: nothing shows it was said to him"
    assert _quotes('Renewal [3].' + sources, 'Health update [sensitive]: the surgery is booked.') == []
    assert _quotes('Renewal [3].' + sources, plain) == [plain]


def test_quoted_words_drop_greeting_and_signature_block():
    result = run_js(['saidWords'], r'''
      console.log(JSON.stringify([
        saidWords('Hi Avery,Good news! The pass is ready at Gate 2.Kind Regards, Mara Ostrowski (she/her) Head of Partnerships T +64 21 555 0100'),
        saidWords('Dear Avery,\nThe renewal can include a fourth seat from 2026-11-01.\n--\nMara\n+64 21 555 0100'),
        saidWords('Thanks for the notes.\nBest regards\nKai Rennick\nM: 021 555 0199')]));
    ''')
    # A sign-off inside the line cuts there and says so with an ellipsis; one on its own line ends the mail.
    assert result == ['Good news! The pass is ready at Gate 2.…', 'The renewal can include a fourth seat from 2026-11-01.', 'Thanks for the notes.']


def test_quoted_words_keep_a_body_that_starts_with_thanks_and_a_phone_inside_a_sentence():
    result = run_js(['saidWords'], r'''
      console.log(JSON.stringify([
        saidWords('Many thanks\nThe slides are attached for Thursday.'),
        saidWords('Call me on +64 21 555 0100 if the gate fails again.'),
        saidWords('The gate works now.\nT +64 21 555 0100\nFernhill Labs'),
        saidWords('The pass is ready at Gate 2. Kind regards, Mara Ostrowski, Head of Partnerships')]));
    ''')
    assert result[0] == 'Many thanks The slides are attached for Thursday.', "a sign-off counts only after a body line"
    assert result[1] == 'Call me on +64 21 555 0100 if the gate fails again.', "a number inside a sentence is not a signature"
    assert result[2] == 'The gate works now.', "a phone line on its own starts the signature"
    assert result[3] == 'The pass is ready at Gate 2.…', "a cut inside a line says so"


def test_owed_parts_drop_a_rest_that_is_only_punctuation_after_date_clutter():
    """"… before internal beta [11] — open as of 2026-11-03." left a lone "." on its own line."""
    result = run_js(['owedParts'], r'''
      const unlabelled = text => text, plainLine = text => text, capFirst = text => text;
      const withoutDateClutter = text => text.replace(/open as of \d{4}-\d{2}-\d{2}/, '').trim();
      console.log(JSON.stringify(owedParts({t: {text: 'Fern asked you to check the plan before beta [11] — open as of 2026-11-03.'}})));
    ''')
    assert result['rest'] == ''
    assert result['head'] == 'Fern asked you to check the plan before beta [11]'
