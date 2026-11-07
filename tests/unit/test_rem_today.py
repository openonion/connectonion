"""Today distinguishes an owner's answer from an unfulfilled promise."""
import json
import re
from datetime import date

import pytest

from connectonion.rem import today
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json
from connectonion.rem.mail_archive import retain_message
from connectonion.rem.reader import TEMPLATE
from connectonion.rem.store import refresh
from test_rem_reader import _run_reader_js


@pytest.mark.parametrize('provider', ['outlook', 'gmail'])
@pytest.mark.parametrize('body,state,quote', [
    ('--- Email Body ---\nHi Mara,\nFriday works. I have sent a calendar invite.\n'
     'https://meet.example.test/mara\n\nThanks,\nAvery\nOn Tuesday Fern wrote:\nI will send feedback.',
     'replied', 'Friday works. I have sent a calendar invite.'),
    ("Hi Fern,\nIntroducing Mara (cc’d), a student interested in the project.\nBest,\nAvery",
     'replied', 'Introducing Mara (cc’d), a student interested in the project.'),
    ("--- Message Body ---\nHi Mara,\nI'll watch it and send feedback that week.\n> Already done.",
     'task', "I'll watch it and send feedback that week."),
    ('邮件正文：\n我下周看演示并发反馈。\n发件人：Fern\n已经发了。', 'task', '我下周看演示并发反馈。'),
])
def test_latest_owner_words_determine_reply_state(tmp_path, rem_clock, provider, body, state, quote):
    prepare(tmp_path)
    write_json(state_path(tmp_path, 'map.json'), {'owner': {'record': 'people/avery.md', 'addresses': ['avery@example.test']}})
    Notebook(tmp_path).write('people/mara.md', '# Mara\n\n## Open threads\n- You owe Mara a reply. [1]\n\n## Sources\n- [1] ' + provider + ':ask\n')
    for identity, sender, stamp, words in [('ask', 'mara@example.test', '2026-10-23', 'Please choose a meeting time.'),
                                           ('answer', 'avery@example.test', '2026-10-28', body)]:
        retain_message(tmp_path, provider, {'id': identity, 'from': sender, 'to': ['avery@example.test', 'mara@example.test'],
                       'thread': 'meeting', 'date': stamp + 'T03:00:00+00:00'}, words, fetched_at='2026-11-08T00:00:00+00:00')
    refresh(tmp_path)
    reply = today.queue(tmp_path, as_of=date(2026, 11, 8))[0]['reply']
    assert reply['state'] == state
    assert reply['last_word_yours'] is True
    assert reply['since'] == '2026-10-28'
    assert reply['promise'] == quote
    assert reply['source'] == provider + ':answer'


@pytest.mark.parametrize('words,promised', [
    ("I'll watch the demo and send feedback.", True),
    ('Sure — I will watch it and send feedback that week.', True),
    ('And I will send the draft tomorrow.', True),
    ('After the demo I will send feedback.', True),
    ('I will review it next week.', True), ('I will send the draft.', True),
    ('Will send feedback tomorrow.', True), ('我会看完后给你反馈。', True),
    ('我下周发给你。', True), ('我明天看一下。', True),
    ('Friday works. I have sent a calendar invite.', False),
    ('I already introduced Mara to Fern.', False), ('我已经发了邀请。', False),
    ('Fern will send it. The demo will be useful.', False),
    ("I won't send it. I will not review it.", False),
    ('I will never send it.', False),
    ('我不会发。', False), ("She said I'll send it.", False),
])
def test_future_commitment_rule_uses_the_owner_as_subject(words, promised):
    assert today._future_commitment(words) is promised


@pytest.mark.parametrize('history', ['> I will send it.', 'On Tuesday Mara wrote:\nI will send it.', '发件人：Mara\n我会发送。'])
def test_quote_removes_scaffolding_history_signatures_and_urls(history):
    body = ('From: Avery <avery@example.test>\nSubject: Fern\n--- Email Body ---\nHi Mara,\n'
            'Friday works. See [the invite](https://example.test/meeting). A third sentence.\n'
            '\nKind regards,\nAvery\nhttps://example.test/signature\n' + history)
    assert today._owner_quote(body) == 'Friday works. See the invite.'


def test_quote_clips_at_a_word_boundary_and_handles_chinese():
    sentence = 'I have sent ' + 'the detailed calendar invitation for Mara and Fern '.strip() * 4 + '.'
    quote = today._owner_quote(sentence)
    assert len(quote) <= 91 and quote.endswith('…')
    assert sentence.startswith(quote[:-1] + ' ')
    assert len(today._owner_quote('我已经发给你了' * 30)) <= 91
    assert today._owner_quote('Thanks,\nAvery') == ''


@pytest.mark.parametrize('tail', ['Sent from my iPhone\nAvery', 'Get Outlook for iOS\nAvery',
                                 '  > I will send feedback.', 'on Tuesday Mara wrote:\nI will send feedback.'])
def test_mobile_signatures_and_indented_history_are_not_owner_words(tail):
    body = 'Hi Fern,\nFriday works.\n' + tail
    assert today._owner_quote(body) == 'Friday works.'
    assert not today._future_commitment(today._owner_words(body))


def reader_functions(*names):
    page = TEMPLATE.read_text()
    return '\n'.join(re.search(r'function ' + name + r'\(.*?\n\}', page, re.S).group(0) for name in names)


@pytest.mark.parametrize('language', ['en', 'zh'])
@pytest.mark.parametrize('status', [None, 'prepared', 'no_reply', 'pending'])
def test_replied_card_offers_completion_first_and_localized_explanation(language, status):
    page = TEMPLATE.read_text()
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    result = _run_reader_js(reader_functions('primaryAction', 'threadActions', 'draftNote') + '\nUI.zh = ' + ui
        + '; uiLanguage = ' + json.dumps(language) + '; const status = ' + json.dumps(status) + ';\n' + r'''
      const REM = {as_of:'2026-11-08', drafts:[], today_queue:[{key:'mara', reply:{state:'replied', last_word_yours:true,
        provider:'outlook', thread:'mail:outlook:meeting', source:'outlook:answer', since:'2026-10-28',
        promise:'Friday works. I have sent a calendar invite.'}}]};
      const entry = {r:{path:'people/mara.md'}, t:{text:'You owe Mara a meeting time.'}};
      const doneKey = () => 'mara', threadKind = () => ({kind:'outlook', mail:true}), isDone = () => false;
      const draft = status ? {status, provider:'outlook', thread:'meeting'} : null;
      if (draft) REM.drafts.push(draft);
      const obligationEvidence = () => ({ids:new Set(['thread:outlook:meeting'])}), fmtDate = day => day, calendarDay = day => day;
      const el = (tag, attrs={}, children=[]) => ({tag, ...attrs, children});
      let completed = false; const setDone = (entry, done) => {completed = done;};
      const actions = threadActions(entry), note = draftNote(draft, entry);
      actions.children.find(node => node?.text === t('Mark done'))?.onclick();
      console.log(JSON.stringify({actions, note, completed}));
    ''')
    actions = [node for node in result['actions']['children'] if node and node.get('tag') in ('button', 'a')]
    assert [(node['text'], node['class']) for node in actions] == [
        ('标为完成' if language == 'zh' else 'Mark done', 'btn-act'),
        ('打开 Outlook 原会话' if language == 'zh' else 'Open the Outlook thread', 'btn-quiet')]
    assert result['completed'] is True
    assert actions[1]['href'].endswith('/answer')
    assert 'Friday works. I have sent a calendar invite.' in result['note']['text']
    assert ('已回复' if language == 'zh' else 'replied') in result['note']['text']
    assert ('如果这件已经办了' if language == 'zh' else 'if this is handled') in result['note']['text']


@pytest.mark.parametrize('provider,label', [('outlook', 'Outlook reply'), ('gmail', 'Gmail reply'), ('lark', 'Lark'), ('session', 'session'), ('', 'Task')])
@pytest.mark.parametrize('prepared', [False, True])
def test_task_state_never_overrides_channel_or_draft_badge(provider, label, prepared):
    if prepared and not provider:
        provider, label = 'gmail', 'Gmail reply'
    result = _run_reader_js(reader_functions('threadKind', 'kindBadge', 'queueCard') + r'''
      const provider = PROVIDER, prepared = PREPARED;
      const entry = {r:{path:'people/fern.md', title:'Fern', category:'people'}, t:{text:provider ? 'You owe Fern feedback [1].' : 'You owe Fern feedback.'}};
      const draft = prepared ? {status:'prepared', provider, thread:'meeting'} : null;
      const REM = {owner:'people/avery.md', source_context:{}, today_queue:[{key:'fern', reply:{state:'task', provider, thread:provider ? 'mail:' + provider + ':meeting' : ''}}]};
      const doneKey = () => 'fern', citationId = () => provider + ':one';
      const sourceChannel = kind => ({gmail:'Gmail', outlook:'Outlook', lark:'Lark', session:'session'}[kind] || kind);
      const threadDraft = () => draft, morningWords = () => ({words:'Feedback', context:''}), contactFields = () => [];
      const company = () => '', calendarDay = day => day, threadWho = r => r.title;
      const href = () => '#fern', blockerTag = () => null, alsoOn = () => null, isDone = () => false;
      const replyDraftCard = () => null, threadActions = () => null, draftNote = () => null;
      const el = (tag, attrs={}, children=[]) => ({tag, ...attrs, children});
      console.log(JSON.stringify(queueCard(entry, '5 days').children[1].children[0]));
    '''.replace('PROVIDER', json.dumps(provider)).replace('PREPARED', json.dumps(prepared)))
    assert result['text'] == label


@pytest.mark.parametrize('state', ['replied', 'task'])
def test_owner_last_card_never_offers_to_send_a_stale_prepared_reply(state):
    result = _run_reader_js(reader_functions('queueCard') + 'const state = ' + json.dumps(state) + ';\n' + r'''
      const entry = {r:{path:'people/fern.md', title:'Fern'}, t:{text:'You owe Fern feedback.'}};
      const REM = {owner:'people/avery.md', today_queue:[{key:'fern', reply:{state, last_word_yours:true}}]};
      const doneKey = () => 'fern', threadDraft = () => ({status:'prepared'});
      const morningWords = () => ({words:'Feedback', context:''}), contactFields = () => [], company = () => '';
      const calendarDay = day => day, threadWho = r => r.title, href = () => '#fern', blockerTag = () => null;
      const kindBadge = () => null, alsoOn = () => null, isDone = () => false, draftNote = () => null;
      const replyDraftCard = () => ({sendable:true}), threadActions = () => ({ownerActions:true});
      const el = (tag, attrs={}, children=[]) => ({tag, ...attrs, children});
      console.log(JSON.stringify(queueCard(entry, '5 days').children[3]));
    ''')
    assert result == {'ownerActions': True}
