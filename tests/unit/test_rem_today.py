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
     'replied', 'Friday works.'),
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


@pytest.mark.parametrize('provider', ['outlook', 'gmail'])
@pytest.mark.parametrize('owner_latest', [False, True])
@pytest.mark.parametrize('citations', ['[1] [2]', '[2] [1]', '[3] [1] [2]'])
def test_reply_uses_newest_message_across_all_cited_threads(tmp_path, rem_clock, provider, owner_latest, citations):
    prepare(tmp_path)
    write_json(state_path(tmp_path, 'map.json'), {'owner': {'record': 'people/avery.md', 'addresses': ['avery@example.test']}})
    Notebook(tmp_path).write('people/fern.md', '# Fern Vale\n\n## Open threads\n'
        '- You owe Fern written feedback on Demo A. ' + citations + '\n\n## Sources\n'
        '- [1] ' + provider + ':promise\n- [2] ' + provider + ':followup\n- [3] ' + provider + ':older\n')
    messages = [
        ('older', 'earlier', 'fern', '2026-10-20', 'Please review Demo A.'),
        ('promise', 'original', 'avery', '2026-10-28', "I'll watch it and send written feedback that week."),
        ('followup', 'feedback', 'fern', '2026-11-01', 'Could you please share your feedback on Demo A?'),
        ('latest', 'original' if owner_latest else 'feedback', 'avery' if owner_latest else 'fern', '2026-11-03',
         "I will send feedback tomorrow." if owner_latest else 'Could you send feedback and your meeting availability?'),
    ]
    for identity, thread, sender, stamp, body in messages:
        retain_message(tmp_path, provider, {'id': identity, 'from': sender + '@example.test',
            'to': ['avery@example.test', 'fern@example.test'], 'thread': thread, 'date': stamp + 'T03:00:00+00:00'},
            body, fetched_at='2026-11-08T00:00:00+00:00')
    refresh(tmp_path)
    reply = today.queue(tmp_path, as_of=date(2026, 11, 8))[0]['reply']
    assert reply['state'] == ('task' if owner_latest else 'queued')
    assert bool(reply.get('last_word_yours')) is owner_latest
    assert reply['source'] == provider + ':latest'
    assert reply['thread'] == 'mail:' + provider + (':original' if owner_latest else ':feedback')
    assert reply['since'] == '2026-11-03'


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
    assert today._owner_quote(body) == 'Friday works.'


@pytest.mark.parametrize('promise', [
    "I'll watch it and send written feedback that week.",
    'I’ll watch it and send written feedback that week.',
    'I will watch it and send written feedback that week.',
    'Will send written feedback that week.',
    '我会看完演示后发书面反馈。',
])
def test_promise_quote_selects_the_commitment_sentence(tmp_path, rem_clock, promise):
    body = ('--- Email Body ---\nHi Fern,\nThank you for the Demo A recording. '
            "I'm in Singapore this week. " + promise + '\n\nBest,\nAvery\n> I will send an unrelated file.')
    prepare(tmp_path)
    write_json(state_path(tmp_path, 'map.json'), {'owner': {'record': 'people/avery.md', 'addresses': ['avery@example.test']}})
    Notebook(tmp_path).write('people/fern.md', '# Fern Vale\n\n## Open threads\n'
        '- You owe Fern written feedback on Demo A. [1]\n\n## Sources\n- [1] outlook:promise\n')
    retain_message(tmp_path, 'outlook', {'id': 'promise', 'from': 'avery@example.test',
        'to': ['fern@example.test'], 'thread': 'demo', 'date': '2026-11-03T03:00:00+00:00'},
        body, fetched_at='2026-11-08T00:00:00+00:00')
    refresh(tmp_path)
    reply = today.queue(tmp_path, as_of=date(2026, 11, 8))[0]['reply']
    assert reply['state'] == 'task'
    assert reply['promise'] == promise


def test_promise_quote_cleans_and_clips_the_selected_sentence():
    promise = 'I will send ' + 'the detailed feedback on Demo A and the revised meeting availability ' * 3 + '.'
    quote = today._owner_quote('Hi Fern,\nThank you for [Demo A](https://example.test/demo). ' + promise)
    assert quote.startswith('I will send ')
    assert len(quote) <= 91 and quote.endswith('…')
    assert promise.startswith(quote[:-1] + ' ')
    assert today._owner_quote('谢谢你发来演示。我会看完后给你反馈。下周再聊。') == '我会看完后给你反馈。'
    assert today._owner_quote('Hi Fern,\nFriday works. See you then.') == 'Friday works.'


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
@pytest.mark.parametrize('status', [None, 'pending'])
def test_replied_card_offers_completion_first_and_localized_explanation(language, status):
    page = TEMPLATE.read_text()
    ui = page[page.index('  zh: {') + len('  zh: '):page.index('\n};\nfunction t(')]
    result = _run_reader_js(reader_functions('primaryAction', 'threadUrl', 'threadActions', 'threadDraft', 'draftNote') + '\nUI.zh = ' + ui
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
    result = _run_reader_js(reader_functions('threadKind', 'kindBadge') + r'''
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
      console.log(JSON.stringify(kindBadge(entry)));
    '''.replace('PROVIDER', json.dumps(provider)).replace('PREPARED', json.dumps(prepared)))
    assert result['text'] == label


@pytest.mark.parametrize('state', ['replied', 'task'])
@pytest.mark.parametrize('status', ['prepared', 'no_reply'])
def test_ready_draft_on_any_cited_thread_beats_owner_last(state, status):
    steps_order = re.search(r'const STEPS = .*?;', TEMPLATE.read_text()).group(0)
    functions = steps_order + reader_functions('personCard', 'cardHead', 'cardItem', 'ownerLine', 'cardDraft', 'stepAction', 'notDoneAction', 'cardStep', 'groupStep',
                                               'threadDraft', 'draftNote', 'mailboxLink', 'threadUrl')
    result = _run_reader_js(functions + 'const state = ' + json.dumps(state) + ', status = ' + json.dumps(status) + ';\n' + r'''
      const entry = {r:{path:'people/fern.md', title:'Fern'}, t:{text:'You owe Fern feedback. [1] [2]'}};
      const draft = {status, provider:'outlook', thread:'feedback', body:'Here is my feedback on Demo A.', gist:'Fern needs no further reply.'};
      const REM = {owner:'people/avery.md', as_of:'2026-11-08', drafts:[{status:'pending', provider:'outlook', thread:'original'},
        {status:'prepared', provider:'gmail', thread:'unrelated'}, draft],
        today_queue:[{key:'fern', reply:{state, last_word_yours:true, provider:'outlook',
          thread:'mail:outlook:original', promise:'I will send feedback.', since:'2026-10-28'}}]};
      const doneKey = () => 'fern', threadKind = () => ({kind:'outlook', mail:true});
      const queuedReply = () => REM.today_queue[0].reply, looksDone = () => false, threadContact = () => null, approvalTask = () => null;
      const obligationEvidence = () => ({ids:new Set(['thread:outlook:original', 'thread:outlook:feedback'])});
      const morningWords = () => ({words:'Feedback', context:''}), contactFields = () => [], company = () => '';
      const calendarDay = day => day, threadWho = r => r.title, href = () => '#fern', blockerTag = () => null, overdueDays = () => 0;
      const kindBadge = () => null, alsoOn = () => null, isDone = () => false, setDone = () => {}, fmtDate = day => day;
      const firstName = r => r.title, threadAge = () => '5 days', taskResult = () => null, CHECK_ICON = '';
      const handedLine = () => null, rowTask = () => null, handOff = () => null;
      const replyDraftCard = draft => ({sendable:true, body:draft.body});
      const el = (tag, attrs={}, children=[]) => ({tag, ...attrs, children});
      const card = personCard({r: entry.r, entries: [entry]}, true);
      const item = card.children[1].children[0];
      console.log(JSON.stringify({draft: card.children[2], note: item.children[2].children[2], acts: card.children[3]}));
    ''')
    if status == 'prepared':
        assert result['draft']['children'][1] == {'sendable': True, 'body': 'Here is my feedback on Demo A.'}
        assert result['note'] is None
        assert 'review-reply' in result['acts']['children'][0]['class']
    else:
        assert result['draft'] is None
        assert result['note']['text'] == 'No reply needed: Fern needs no further reply.'
        assert result['acts']['children'][0]['text'] == 'Mark done'
        assert result['acts']['children'][0]['class'] == 'btn-act'


def test_today_groups_a_persons_rows_into_their_first_card_without_reranking():
    """Two asks from the same person are one card, placed where Python ranked the first."""
    result = _run_reader_js(reader_functions('personGroups') + r'''
      const row = (path, n) => ({r: {path}, t: {text: 'ask ' + n}});
      const groups = personGroups([row('people/ody.md', 1), row('people/jie.md', 2), row('people/ody.md', 3), row('orgs/rmit.md', 4)]);
      console.log(JSON.stringify(groups.map(g => [g.r.path, g.entries.map(e => e.t.text)])));
    ''')
    assert result == [['people/ody.md', ['ask 1', 'ask 3']], ['people/jie.md', ['ask 2']], ['orgs/rmit.md', ['ask 4']]]


@pytest.mark.parametrize('live', [False, True])
def test_today_primary_is_the_most_likely_next_step_never_the_mailbox(live):
    steps_order = re.search(r'const STEPS = .*?;', TEMPLATE.read_text()).group(0)
    result = _run_reader_js(steps_order + reader_functions('cardStep', 'groupStep', 'entryKeys', 'approvalTask') + r'''
      const REM = {live: LIVE, approval_outcomes: [{kind: 'task', keys: ['task']}]};
      const rows = {
        draft: {draft: {status: 'prepared'}}, queued: {reply: {state: 'queued', thread: 'mail:gmail:x'}},
        task: {reply: {state: 'task'}}, handled: {looks: true}, noReply: {draft: {status: 'no_reply'}},
        overdueReplied: {reply: {state: 'replied'}, contact: true}, nothing: {}};
      const entry = key => ({key, ...rows[key]});
      const doneKey = entry => entry.key, threadDraft = entry => entry.draft, queuedReply = entry => entry.reply;
      const looksDone = entry => !!entry.looks, threadContact = entry => entry.contact ? {address: 'a@example.test'} : null, threadKind = () => null;
      const steps = Object.fromEntries(Object.keys(rows).map(key => [key, cardStep(entry(key))]));
      const mixed = groupStep([entry('handled'), entry('overdueReplied')]);
      const tie = groupStep([entry('overdueReplied'), {...entry('overdueReplied'), key: 'second'}]);
      console.log(JSON.stringify({steps, mixed: [mixed.step, mixed.entry.key], tie: tie.entry.key}));
    '''.replace('LIVE', json.dumps(live)))
    steps = result['steps']
    assert steps['draft'] == 'send'
    assert steps['queued'] == ('draft' if live else 'live')  # a snapshot names the live reader, never a dead end
    assert steps['task'] == ('approve' if live else 'open')
    assert steps['handled'] == 'done' and steps['noReply'] == 'done'
    # A reply after the promise fell due does not settle it: write, not "mark done".
    assert steps['overdueReplied'] == 'write'
    assert steps['nothing'] == 'open'
    assert result['mixed'] == ['write', 'overdueReplied']
    assert result['tie'] == 'overdueReplied'


def test_palette_fuzzy_match_ranks_word_starts_and_accepts_words_in_any_order():
    result = _run_reader_js(reader_functions('subsequenceScore', 'fuzzyScore') + r'''
      const score = (q, s) => fuzzyScore(q, s);
      console.log(JSON.stringify({
        miss: score('xyz', 'Alyssa Lubrano'), hit: score('alu', 'Alyssa Lubrano') >= 0,
        start: score('al', 'Alyssa Lubrano') > score('al', 'Natalie Lin'),
        order: score('起草 alyssa', '给 Alyssa 起草回信') >= 0, today: score('打开今天', '打开今天') > 0,
        empty: score('', 'anything'), accent: score('ines', 'Inès Halvorsen') > 0, whole: score('mark mara done', 'Mark Mara Ostrowski done') > score('mark mara done', 'Mark Harbour done')}));
    ''')
    assert result == {'miss': -1, 'hit': True, 'start': True, 'order': True, 'today': True, 'empty': 0, 'accent': True, 'whole': True}


def test_today_keys_never_fire_while_typing():
    result = _run_reader_js(reader_functions('typingIn') + r'''
      const target = tag => ({closest: selector => selector.split(',').some(s => s.trim().startsWith(tag)) ? {} : null});
      console.log(JSON.stringify(['input', 'textarea', 'select', 'li', 'button'].map(tag => typingIn(target(tag)))));
    ''')
    assert result == [True, True, True, False, False]


def test_today_card_speaks_chinese_where_rem_already_wrote_it():
    """On 中文 the card's line is the draft's Chinese gist; English stays the original, private stays out."""
    import json
    import re
    import shutil
    import subprocess
    from connectonion.rem.reader import TEMPLATE
    node = shutil.which("node")
    if not node:
        pytest.skip("Node runs the reader JavaScript")
    page = TEMPLATE.read_text()
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0) for name in ["t", "ownerLine"])
    ui = 'const UI = {en: {}, zh: {"REM drafted: ": "REM 已起草：", "No reply needed: ": "不用回："}};\n'
    script = ui + "let uiLanguage = 'zh';\n" + functions + r"""
      const prepared = {status: 'prepared', gist: '草稿回答了两个问题，未发送。'};
      const out = {zh: ownerLine(prepared), noReply: ownerLine({status: 'no_reply', gist: '对方已确认，不用回。'}),
        english: ownerLine({status: 'prepared', gist: 'Answers both questions.'}),
        secret: ownerLine({...prepared, private: true}), pending: ownerLine({status: 'pending', gist: '还在写。'}), none: ownerLine(null)};
      uiLanguage = 'en'; out.en = ownerLine(prepared);
      console.log(JSON.stringify(out));
    """
    result = subprocess.run([node], input=script, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"zh": "REM 已起草：草稿回答了两个问题，未发送。", "noReply": "不用回：对方已确认，不用回。",
                                         "english": None, "secret": None, "pending": None, "none": None, "en": None}
