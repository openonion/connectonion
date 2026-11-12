"""One deterministic, quiet morning note, claimed before external delivery."""

from datetime import date, datetime, timedelta
from pathlib import Path
import os
import re
import sys

from . import approvals, service
from .config import read_config
from .files import maintenance_lock, read_json, state_path, write_json


# outlook: the owner's own personal mailbox, from and to itself, as a designed mail.
CHANNELS = ('outlook', 'telegram', 'lark', 'whatsapp', 'email')  # Email is the last choice.
# A note is due from 06:00 until 11:00 local. Later it is no longer a morning note: a
# sleeping laptop or schedule.times' own "17:00" slot would otherwise say 「昨夜」 at dusk.
OPENS, CLOSES = 6, 11
KEEP_DAYS = 14
# rem/problems.py verdict states whose explanation the owner can now read.
EXPLAINED = ('explained', 'needs_owner', 'fix_proposed')


def _local(config):
    return service.now().astimezone(service.notebook_zone(config))


def _markers(root):
    return read_json(state_path(root, 'morning.json'), {})


def _previous(saved, day):
    """The latest earlier claim. A missed date reported nothing, so it does not move the window."""
    earlier = [saved[date] for date in sorted(saved) if date < day and saved[date].get('status') != 'missed']
    return earlier[-1] if earlier else None


def _start(local, previous):
    # From the last note to now, so work after 06:00 and before the check is reported once.
    if previous and previous.get('checked_at'):
        return datetime.fromisoformat(previous['checked_at'])
    return local.replace(hour=22, minute=0, second=0, microsecond=0) - timedelta(days=1)


def _within(value, start, end):
    if not value:
        return False
    moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return moment.tzinfo is not None and start < moment <= end


def overnight(root, start, end):
    """What REM did between start and end, as rows the note and the mail both read."""
    night = list(read_json(state_path(root, 'night.json'), {}).get('items', {}).values())
    receipts = {}
    for path in state_path(root, 'drafts').glob('*.json'):
        draft = read_json(path, {})
        receipts[draft.get('id') or path.stem] = draft
    # night.json is a current projection and sent replies may have left it; the
    # draft receipts keep them. A draft is "waiting" only while it is still prepared.
    # Who a draft answers: the night row that prepared it, by draft id or by the mail it replies to.
    people = {row[key]: row for entry in night for key in ('draft_id', 'source')
              if (row := entry.get('outcome', {})).get(key)}
    drafted = {row.get('draft_id') or str(index) for index, entry in enumerate(night)
               if (row := entry.get('outcome', {})).get('kind') == 'prepared'
               and _within(row.get('prepared_at'), start, end)}
    drafted |= {id for id, draft in receipts.items() if draft.get('status') in ('prepared', 'held', 'sent')
                and _within(draft.get('prepared_at'), start, end)}
    queue = read_json(state_path(root, 'approvals.json'), {}).values()
    replies = [row for row in queue if row.get('kind') == 'reply' and row.get('by') == 'rem']
    tasks = [read_json(path, {}) for path in state_path(root, 'tasks').glob('do-*/receipt.json')]
    # rem/problems.py writes {problem key: receipt}; every save() bumps updated_at.
    problems = read_json(state_path(root, 'investigations/index.json'), {}).values()
    return {'sent': [row for row in replies if row.get('status') == 'sent' and _within(row.get('release_at'), start, end)],
            # Held: REM released it and the undo window is still open.
            'holding': [row for row in replies if row.get('status') == 'held'],
            'drafted': [{**people.get(receipts.get(id, {}).get('version'), people.get(id, {})), **receipts.get(id, {})}
                        for id in sorted(drafted, key=lambda id: receipts.get(id, {}).get('prepared_at', ''), reverse=True)
                        if receipts.get(id, {}).get('status', 'prepared') == 'prepared'],
            'finished': [row for row in tasks if row.get('result') == 'completed' and _within(row.get('finished_at'), start, end)],
            'explained': [row for row in problems if row.get('state') in EXPLAINED and _within(row.get('updated_at'), start, end)]}


def counts(root, start, end):
    done = overnight(root, start, end)
    return {name: len(done[name]) for name in ('sent', 'drafted', 'finished', 'explained')}


def sent_by_rem(root, start=None, end=None):
    """Who REM replied to on its own (direct send), in send order, for Today and the morning note."""
    queue = read_json(state_path(root, 'approvals.json'), {}).values()
    rows = [row for row in queue if row.get('kind') == 'reply' and row.get('by') == 'rem'
            and row.get('status') == 'sent' and (start is None or _within(row.get('release_at'), start, end))]
    return [{'title': row.get('title', ''), 'text': row.get('text', ''), 'sent_at': row.get('release_at')}
            for row in sorted(rows, key=lambda row: row.get('release_at') or '')]


def actionable(root):
    """Only current, unblocked owner actions; held replies need no click."""
    return [row for row in approvals.outcomes(root) if not row.get('blocked')]


def today_link(root):
    from ..project import project_identity
    from .reader import LIVE_REM_URL, host_online
    # Only the default notebook is exposed by the Host's /rem route.
    if Path(root).resolve() == (Path.home() / '.co/rem').resolve():
        identity = project_identity()
        address = identity.get('address') if identity else None
        if address and host_online(address):
            return LIVE_REM_URL.format(address=address)
    return 'co rem open'


def _plain(value, limit):
    # Owner-facing words only: never an address, a record path or an ID.
    text = ' '.join(str(value or '').split())
    if '@' in text or '\\' in text or re.search(r'(^|\s)[~/]|\.(md|html?|py|json|ya?ml|pdf|docx?|xlsx?|csv|txt|png|jpe?g)\b|\b[0-9a-f]{16,}\b', text, re.I):
        return ''
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def _summary(c, zh):
    if zh:
        replies = [f"替你发出 {c['sent']} 封回复" if c['sent'] else '',
                   (f"另拟好 {c['drafted']} 封待你看" if c['sent'] else f"拟好 {c['drafted']} 封回复待你看") if c['drafted'] else '']
        work = [f"跑完 {c['finished']} 项任务" if c['finished'] else '', f"查清 {c['explained']} 个问题" if c['explained'] else '']
        return '昨夜：' + '；'.join('，'.join(filter(None, group)) for group in (replies, work) if any(group)) + '。'
    replies = [_plural(c['sent'], 'reply', 'replies') + ' sent for you' if c['sent'] else '',
               (f"{c['drafted']} more" if c['sent'] else _plural(c['drafted'], 'reply', 'replies')) + ' drafted for you to check'
               if c['drafted'] else '']
    work = [_plural(c['finished'], 'task', 'tasks') + ' finished' if c['finished'] else '',
            _plural(c['explained'], 'problem', 'problems') + ' explained' if c['explained'] else '']
    return 'Overnight: ' + '; '.join(', '.join(filter(None, group)) for group in (replies, work) if any(group)) + '.'


def _decision(row, zh):
    """One clause from the row's own kind and words; the cost comes first."""
    who, words = _plain(row.get('title'), 60), _plain(row.get('text') or row.get('subject'), 40)
    if row.get('kind') == 'reply':
        if zh:
            return '以你的名义回' + (f' {who}' if who else '复') + (f'（{words}）' if words else '') + '——用我拟的稿？'
        return 'Reply' + (f' to {who}' if who else '') + ' as you' + (f' ({words})' if words else '') + ' — send my draft?'
    if row.get('kind') == 'task':
        subject = who or words or ('一项任务' if zh else 'A task')
        return f'{subject}——花一次 Codex 运行去做，还是先放着？' if zh else f'{subject} — spend one Codex run on it, or leave it?'
    subject = who or words or ('一件事' if zh else 'One thread')
    return f'{subject}——不用再回了，标为已处理？' if zh else f'{subject} — no reply needed; mark it done?'


def _zh(root, config):
    """The owner's main detected language decides; config.language is only the fallback."""
    from .languages import owner_languages
    return (owner_languages(root)['languages'] or [config['language']])[0].lower().startswith('zh')


def compose(root, config, local, saved, link):
    """Read-only: the exact note for `local`, given earlier markers; '' means stay quiet."""
    zh = _zh(root, config)
    previous = _previous(saved, local.date().isoformat())
    done, pending = overnight(root, _start(local, previous), local), actionable(root)
    # Sending as him outranks starting work, which outranks closing a thread.
    pending = sorted(pending, key=lambda row: ('reply', 'task').index(row.get('kind')) if row.get('kind') in ('reply', 'task') else 2)
    totals = {name: len(done[name]) for name in ('sent', 'drafted', 'finished', 'explained')}
    ids = sorted(row.get('id', '') for row in pending)
    lines = [_summary(totals, zh)] if any(totals.values()) else []
    names = list(dict.fromkeys(filter(None, (_plain(row['title'], 60) for row in sent_by_rem(root, _start(local, previous), local)))))
    if names:
        lines.append(('替你回了：' if zh else 'Replied for you: ') + ('、' if zh else ', ').join(names))
    if pending:
        n = len(pending)
        lines.append(f'{n} 件要你拍板：' if zh else f"{n} decision{'s' if n > 1 else ''}:")
        lines += ['· ' + _decision(row, zh) for row in pending[:2]]
        if n > 2:
            lines.append(f'还有 {n - 2} 件在 Today' if zh else f'{n - 2} more in Today')
    # Nothing new overnight and the same open decisions as last time: say nothing again.
    repeat = not any(totals.values()) and previous is not None and previous.get('pending') == ids
    if lines and not repeat:
        lines.append(('打开 Today：' if zh else 'Open Today: ') + link)
    message = '' if repeat else '\n'.join(lines)
    names = {row['draft_id']: row.get('title') for row in pending if row.get('draft_id')}
    done['drafted'] = [{'title': names.get(row.get('id')), **{k: v for k, v in row.items() if v}} for row in done['drafted']]
    mail = _mail(done, pending, local, zh, link) if message else {'subject': '', 'html': ''}
    return {'channel': config['notify']['channel'], 'message': message, **mail, 'counts': totals, 'pending': ids}


# ---------- the morning mail: one column, table layout, inline styles ----------
INK, BODY, MUTED, RULE, PAPER, CANVAS = '#0f1a14', '#2b332e', '#6b736e', '#e6e2da', '#ffffff', '#f3f1ec'
ALARM, GREEN, GREEN_INK = '#e2401c', '#22d27a', '#05301b'
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei',Helvetica,Arial,sans-serif"
WORDS = {
    # A draft is prepared, not done: the lead names drafts and sends apart, so 13 drafts
    # and no send never reads as "13 things done".
    True: {'brand': 'REM 早报', 'did': '昨夜 REM 替你{parts}', 'replies': '拟好 {p} 份回信，发出 {s} 封',
           'tasks': '做完 {n} 项任务', 'problems': '查清 {n} 个问题', 'join': '；', 'count': ' · {n} 件', 'calm': '昨夜没有新动静', 'need': '{n} 件要你拍板', 'below': '，在下面',
           'sent': '已替你发出', 'holding': '正在发出，可撤回', 'drafted': '草稿已拟好，等你看', 'finished': '任务已做完',
           'explained': '问题已查清', 'sent_at': '{t} 发出', 'until': '{t} 前可撤回', 'undo': '撤回', 'open_one': '打开看结果',
           'reply': '看稿并发送', 'task': '决定做不做', 'handled': '不用回，标为已处理', 'more': '还有 {n} 件在 Today',
           'more_done': '另有 {n} 件在 Today', 'today': '打开 Today', 'no_link': 'Today 现在打不开：这台电脑上的 REM 不在线。',
           'quiet': 'REM 每天早上最多发一封；没有事就不发。', 'subject': 'REM 早报 · {did}', 'subject_need': '，{n} 件要你拍板',
           'states': {'explained': '已查清', 'needs_owner': '需要你', 'fix_proposed': '已拟修复'},
           'date': '{m}月{d}日 {w}', 'week': '周一 周二 周三 周四 周五 周六 周日'},
    False: {'brand': 'REM morning', 'did': 'Overnight, REM {parts}', 'replies': 'drafted {p} for you and sent {s}',
            'tasks': 'finished {n}', 'problems': 'explained {n}', 'join': '; ', 'count': ' · {n} items', 'calm': 'A quiet night',
            'need': '{n} need you', 'below': ' — below', 'sent': 'Sent for you', 'holding': 'Sending — you can still undo',
            'drafted': 'Drafts ready for you', 'finished': 'Tasks finished', 'explained': 'Problems explained',
            'sent_at': 'sent {t}', 'until': 'undo until {t}', 'undo': 'Undo', 'open_one': 'Open the result',
            'reply': 'Review and send', 'task': 'Decide', 'handled': 'No reply needed — mark done', 'more': '{n} more in Today',
            'more_done': '{n} more in Today', 'today': 'Open Today', 'no_link': "Today can't open right now: REM on this computer is offline.",
            'quiet': 'REM sends at most one note a morning, and nothing on a quiet one.', 'subject': 'REM morning · {did}',
            'subject_need': ', {n} need you', 'states': {'explained': 'explained', 'needs_owner': 'needs you', 'fix_proposed': 'fix proposed'},
            'date': '{w} {d} {mon}', 'week': 'Mon Tue Wed Thu Fri Sat Sun'}}
SHOWN = 4  # rows per group; the rest wait in Today


def _e(text):
    from html import escape
    return escape(text, quote=True)


def _subject_line(value):
    return re.sub(r'^(?:(?:re|fw|fwd|回复|答复|转发)\s*[:：]\s*)+', '', _plain(value, 80), flags=re.I)


def _page(row):
    return row.get('record') or (row.get('keys') or [''])[0].split('\n')[0]


def _at(value, local):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(local.tzinfo).strftime('%H:%M')


def _deep(link, record):
    """The live reader at that page; '' when there is no live reader to open."""
    from urllib.parse import quote
    if not link.startswith('http'):
        return ''
    return link + ('#r=' + quote(record, safe='/') if record else '')


def _done_rows(done, local, w, link):
    """(group label, [(name, subject, detail, href, href label)]) in the owner's reading order."""
    private = lambda row, text: '' if row.get('private') else text
    groups = [
        ('holding', [(_plain(r.get('title'), 40), private(r, _subject_line(r.get('subject'))),
                      w['until'].format(t=_at(r['release_at'], local)), link if link.startswith('http') else '', w['undo'])
                     for r in done['holding'] if r.get('release_at')]),
        ('sent', [(_plain(r.get('title'), 40), private(r, _subject_line(r.get('subject'))),
                   w['sent_at'].format(t=_at(r['release_at'], local)), '', '') for r in done['sent']]),
        ('drafted', [(_plain(r.get('title'), 40), private(r, _subject_line(r.get('subject'))),
                      private(r, _plain(r.get('gist'), 90)), '', '') for r in done['drafted']]),
        ('finished', [(_plain(r.get('title'), 40), '', _plain(r.get('text'), 110), _deep(link, _page(r)), w['open_one'])
                      for r in done['finished']]),
        ('explained', [(_plain(r.get('symptom'), 60), _plain((r.get('repo') or '').split('/')[-1], 40), w['states'].get(r.get('state'), '') if r.get('state') != 'explained' else '', '', '')
                       for r in done['explained']])]
    return [(w[name], rows) for name, rows in groups if rows]


def _button(label, href, primary):
    fill, ink, edge = (GREEN, GREEN_INK, GREEN) if primary else (PAPER, INK, INK)
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:14px"><tr>'
            f'<td class="{"btn" if primary else "btn2"}" bgcolor="{fill}" style="background:{fill};border:2px solid {edge}">'
            f'<a href="{_e(href)}" style="display:inline-block;padding:11px 20px;font:700 15px/1 {FONT};color:{ink};'
            f'text-decoration:none">{_e(label)}&nbsp;&rarr;</a></td></tr></table>')


def _row(name, subject, detail, href, label):
    head = f'<span class="ink" style="color:{INK};font-weight:700">{_e(name)}</span>' if name else ''
    if subject:
        head += (f'<span class="mute" style="color:{MUTED}"> &middot; </span>' if name else '') + \
            f'<span class="body" style="color:{BODY}">{_e(subject)}</span>'
    tail = _e(detail)
    if href:
        tail += (' &middot; ' if detail else '') + f'<a href="{_e(href)}" class="ink" style="color:{INK};font-weight:600">{_e(label)}</a>'
    tail = f'<div class="mute" style="color:{MUTED};font-size:13px;line-height:20px;margin-top:2px">{tail}</div>' if tail else ''
    return (f'<tr><td class="rule" style="padding:12px 0;border-top:1px solid {RULE};font:15px/22px {FONT}">'
            f'{head}{tail}</td></tr>')


def _group(label, rows, w):
    more = len(rows) - SHOWN
    body = ''.join(_row(*row) for row in rows[:SHOWN])
    if more > 0:
        body += (f'<tr><td class="mute rule" style="padding:10px 0;border-top:1px solid {RULE};color:{MUTED};'
                 f'font:13px/20px {FONT}">{_e(w["more_done"].format(n=more))}</td></tr>')
    return (f'<tr><td style="padding:28px 0 4px;font:700 12px/16px {FONT};letter-spacing:.08em;color:{MUTED}" class="mute">'
            f'{_e(label.upper())}</td></tr>{body}')


def _by_person(pending):
    """One decision per person: their items together, in the order the first one came."""
    people = {}
    for row in pending:
        people.setdefault(_page(row) or row.get('title') or row.get('id'), []).append(row)
    return list(people.values())


def _name(row):
    return _plain(row.get('title'), 60) or _subject_line(row.get('subject'))


def _words(row):
    subject = _subject_line(row.get('subject'))
    return _plain(row.get('text'), 120) or (subject if _name(row) != subject else '')


def _decisions(pending, zh, w, link):
    if not pending:
        return ''
    blocks, people = '', _by_person(pending)
    for index, rows in enumerate(people[:3]):
        row = rows[0]
        name = _name(row) + (w['count'].format(n=len(rows)) if len(rows) > 1 else '')
        words = w['join'].join(dict.fromkeys(filter(None, map(_words, rows))))
        href = _deep(link, _page(row))
        button = _button(w.get(row.get('kind'), w['handled']), href, index == 0) if href else ''
        blocks += (f'<tr><td class="rule" style="padding:18px 0 20px;border-top:1px solid {RULE}">'
                   f'<div class="ink" style="font:700 17px/24px {FONT};color:{INK}">{_e(name)}</div>'
                   f'<div class="body" style="font:15px/23px {FONT};color:{BODY};margin-top:4px">{_e(words)}</div>'
                   f'{button}</td></tr>')
    more = len(pending) - sum(map(len, people[:3]))
    if more > 0:
        blocks += (f'<tr><td class="mute rule" style="padding:12px 0;border-top:1px solid {RULE};color:{MUTED};'
                   f'font:13px/20px {FONT}">{_e(w["more"].format(n=more))}</td></tr>')
    return (f'<tr><td style="padding:40px 0 10px"><table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td width="12" height="12" bgcolor="{ALARM}" class="alarm" style="background:{ALARM};width:12px;height:12px;font-size:0;line-height:0">&nbsp;</td>'
            f'<td style="padding-left:10px;font:700 20px/24px {FONT};color:{INK}" class="ink">{_e(w["need"].format(n=len(pending)))}</td>'
            f'</tr></table></td></tr>{blocks}')


def _date(local, w, zh):
    day = w['week'].split()[local.weekday()]
    return w['date'].format(m=local.month, d=local.day, w=day, mon=local.strftime('%b'))


DARK = (f'@media (prefers-color-scheme: dark){{.canvas{{background:#0c110e!important}}.card{{background:#141b17!important}}'
        f'.ink{{color:#eef2ef!important}}.body{{color:#c9d0cb!important}}.mute{{color:#8f9893!important}}'
        f'.rule{{border-color:#26302a!important}}.bar{{background:#eef2ef!important}}.alarm{{background:#ff5a36!important}}.alarm-text{{color:#ff6a48!important}}'
        f'.btn2{{background:#141b17!important;border-color:#eef2ef!important}}.btn2 a{{color:#eef2ef!important}}}}'
        f'[data-ogsc] .ink{{color:#eef2ef!important}}[data-ogsc] .body{{color:#c9d0cb!important}}[data-ogsc] .mute{{color:#8f9893!important}}'
        f'@media (max-width:620px){{.card{{padding:28px 20px 24px!important}}.lead{{font-size:25px!important;line-height:33px!important}}}}')


def _lead(done, w, zh):
    """Drafts count as prepared and sends as sent; only tasks and problems are done."""
    sent = len(done['sent']) + len(done['holding'])
    prepared, finished, explained = len(done['drafted']) + sent, len(done['finished']), len(done['explained'])
    say = (lambda n, one, many: n) if zh else _plural
    parts = [w['replies'].format(p=say(prepared, 'reply', 'replies'), s=sent) if prepared else '',
             w['tasks'].format(n=say(finished, 'task', 'tasks')) if finished else '',
             w['problems'].format(n=say(explained, 'problem', 'problems')) if explained else '']
    parts = [part for part in parts if part]
    return w['did'].format(parts=w['join'].join(parts)) if parts else w['calm']


def _mail(done, pending, local, zh, link):
    """The same morning as the note, as a designed mail: what REM did first, then one decision per person for up to three people."""
    w = WORDS[zh]
    groups = _done_rows(done, local, w, link)
    lead = _lead(done, w, zh)
    subject = w['subject'].format(did=lead) + (w['subject_need'].format(n=len(pending)) if pending else '')
    need = (f'<span class="alarm-text" style="color:{ALARM};font-weight:700">{_e(w["need"].format(n=len(pending)))}'
            f'{_e(w["below"])}</span>') if pending and groups else ''
    sub = need
    footer = (f'<a href="{_e(link)}" class="ink" style="color:{INK};font-weight:700;text-decoration:underline">{_e(w["today"])}</a>'
              if link.startswith('http') else _e(w['no_link']))
    html = f'''<!DOCTYPE html>
<html lang="{'zh-CN' if zh else 'en'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">
<title>{_e(subject)}</title><style>{DARK}</style></head>
<body class="canvas" style="margin:0;padding:0;background:{CANVAS}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{_e(lead)}</div>
<table role="presentation" class="canvas" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{CANVAS}" style="background:{CANVAS}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px">
<tr><td><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td width="72" height="6" bgcolor="{ALARM}" class="alarm" style="background:{ALARM};height:6px;font-size:0;line-height:0">&nbsp;</td>
<td height="6" bgcolor="{INK}" class="bar" style="background:{INK};height:6px;font-size:0;line-height:0">&nbsp;</td></tr></table></td></tr>
<tr><td class="card" bgcolor="{PAPER}" style="background:{PAPER};padding:36px 40px 32px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td style="font:700 12px/16px {FONT};letter-spacing:.08em;color:{INK}" class="ink">{_e(w['brand'].upper())}
<span class="mute" style="color:{MUTED};font-weight:400;letter-spacing:0">&nbsp;&nbsp;{_e(_date(local, w, zh))}</span></td></tr>
<tr><td class="ink lead" style="padding-top:18px;font:700 30px/38px {FONT};color:{INK}">{_e(lead)}</td></tr>
{f'<tr><td class="mute" style="padding-top:8px;font:14px/21px {FONT};color:{MUTED}">{sub}</td></tr>' if sub else ''}
{''.join(_group(label, rows, w) for label, rows in groups)}
{_decisions(pending, zh, w, link)}
<tr><td class="rule mute" style="padding-top:28px;border-top:1px solid {RULE};font:14px/22px {FONT};color:{MUTED}">{footer}
<div style="padding-top:6px;font-size:12px;line-height:18px">{_e(w['quiet'])}</div></td></tr>
</table></td></tr></table></td></tr></table></body></html>'''
    return {'subject': subject, 'html': html}


def preview(root):
    config = read_config(root)
    return compose(root, config, _local(config), _markers(root), today_link(root))


def _plan(local, entry, value):
    """What a real run would do now, in one line, for --dry-run."""
    if entry:
        at = datetime.fromisoformat(entry['checked_at']).astimezone(local.tzinfo).strftime('%H:%M')
        return f'already sent {at}' if entry['status'] == 'sent' else \
            f"already checked {at} ({entry['status']}): nothing more today"
    if value['channel'] == 'none':
        return 'channel none: nothing will be sent'
    if local.hour < OPENS:
        return f'not due until {OPENS:02d}:00'
    if local.hour >= CLOSES:
        return f'outside the morning window ({OPENS:02d}:00–{CLOSES:02d}:00): nothing will be sent today'
    return f"would send now via {value['channel']}" if value['message'] else 'quiet: nothing to send'


def _preview_file(day, value):
    """The outlook mail as a file to open in a browser; nothing for chat channels."""
    import tempfile
    if value['channel'] != 'outlook' or not value['html']:
        return ''
    path = Path(tempfile.gettempdir()) / f'rem-morning-{day}.html'
    path.write_text(value['html'], encoding='utf-8')
    return str(path)


def _record(root, day, entry):
    """Write one date's marker and keep only the last KEEP_DAYS days."""
    oldest = (date.fromisoformat(day) - timedelta(days=KEEP_DAYS)).isoformat()
    saved = {key: value for key, value in _markers(root).items() if key >= oldest}
    saved[day] = entry
    write_json(state_path(root, 'morning.json'), saved)


def send_message(channel, target, message, html='', subject=''):
    """Use precisely the existing CLI send paths, including their test seams."""
    from contextlib import redirect_stdout
    from io import StringIO
    from .files import RemError
    if channel == 'outlook':
        return _send_outlook(target, message, html, subject)
    if not target.strip():
        raise RemError('Set notify.target to your own chat or personal email address')
    # Existing handlers own formatting, listener startup, transport and send receipts.
    with redirect_stdout(StringIO()):
        if channel == 'telegram':
            from ..cli.commands.telegram_commands import handle_telegram_send
            handle_telegram_send(target, message)
        elif channel == 'email':
            from ..useful_tools.send_email import send_email
            result = send_email(target, 'REM · Today', message)
            if not result.get('success'):
                raise RemError('Email delivery not confirmed; inspect co email sent')
        else:
            from ..cli.commands.listen_commands import handle_send
            handle_send(channel, target, message, plain=True)


def _send_outlook(target, message, html, subject):
    """From the linked Outlook mailbox to that same mailbox: personal content stays in it."""
    from ..useful_tools.outlook import Outlook
    from .files import RemError
    mailbox = Outlook()
    own = mailbox.my_addresses()
    to = target.strip().lower() or next(iter(own), '')
    if not to or to not in own:
        raise RemError('notify.target must be the linked Outlook mailbox itself; leave it empty to use it')
    # Graph takes one body; Exchange adds the text/plain part when it leaves the mailbox.
    mailbox.send(to, subject, message, html=html)


def run(root, *, dry_run=False):
    config = read_config(root)
    local = _local(config)
    day = local.date().isoformat()
    if dry_run:
        saved = _markers(root)
        value = compose(root, config, local, saved, today_link(root))
        return {**value, 'plan': _plan(local, saved.get(day), value), 'file': _preview_file(day, value)}
    if local.hour < OPENS:
        return {'status': 'not_due'}
    if day in (saved := _markers(root)):
        return saved[day]
    # host_online may wait 3s on the network: decide the link before taking the write lock.
    link = today_link(root) if local.hour < CLOSES else ''
    with maintenance_lock(root):
        saved = _markers(root)
        if day in saved:
            return saved[day]
        entry = {'status': 'missed', 'channel': config['notify']['channel'], 'checked_at': service.now().isoformat()}
        if local.hour < CLOSES:
            # An error here claims nothing: scheduled_check reports it and the next tick retries.
            value = compose(root, config, local, saved, link)
            entry.update(status='sending' if value['message'] and value['channel'] != 'none'
                         else 'disabled' if value['message'] else 'quiet', pending=value['pending'])
        _record(root, day, entry)
    if entry['status'] != 'sending':
        return entry
    try:
        send_message(value['channel'], config['notify']['target'], value['message'], value['html'], value['subject'])
        entry['status'] = 'sent'
    except (Exception, SystemExit) as error:
        # Delivery can be ambiguous. Never retry; doctor carries the safe diagnosis.
        entry.update(status='failed', error=type(error).__name__)
    with maintenance_lock(root):
        _record(root, day, entry)
    return entry


def sender_status():
    from ..inbox import provider
    from ..environment import load_environment
    load_environment()
    result = []
    for channel in CHANNELS:
        if channel == 'outlook':
            from ..provider_credentials import resolve_provider_credentials
            microsoft = resolve_provider_credentials('microsoft')
            configured = bool(microsoft.get('ACCESS_TOKEN') or microsoft.get('REFRESH_TOKEN'))
            fix = 'co auth microsoft'
        elif channel == 'email':
            configured = bool(os.environ.get("OPENONION_API_KEY"))
            fix = 'co auth login'
        else:
            sender = provider(channel)
            configured = not (sender.linked() if channel == 'whatsapp' else sender.missing())
            fix = f'co {channel} check'
        result.append({'channel': channel, 'configured': configured,
                       'next': ('co rem config set notify.channel outlook' if channel == 'outlook' else
                                f'co rem config set notify.target YOUR_OWN_CHAT notify.channel {channel}') if configured else fix})
    return result


def doctor(root):
    config = read_config(root)
    senders = sender_status()
    rows = [{'check': 'morning sender ' + item['channel'], 'ok': True,
             'detail': ('configured' if item['configured'] else 'not configured') + '; next: ' + item['next']}
            for item in senders]
    selected = config['notify']['channel']
    sender = next((item for item in senders if item['channel'] == selected), {})
    ready = (selected == 'outlook' or bool(config['notify']['target'])) and sender.get('configured', False)
    rows.append({'check': 'morning channel', 'ok': selected == 'none' or ready,
                 'detail': selected if selected == 'none' or ready else selected + '; setup incomplete',
                 'fix': sender.get('next', 'co rem morning --help')})
    saved = _markers(root)
    latest = max(saved, default=None)  # A later good morning supersedes an old failure.
    if latest and saved[latest]['status'] in ('failed', 'sending'):
        rows.append({'check': 'morning delivery', 'ok': False,
                     'detail': f"{latest}: {saved[latest]['status']}; no automatic retry",
                     'fix': 'co rem morning --dry-run; co rem doctor'})
    return rows


def scheduled_check(root):
    """Notification IO must never stop the round (including a busy writer)."""
    try:
        return run(root)
    except Exception as error:
        # A claimed date remains visible in doctor even if receipt finalization fails.
        print(f"REM morning check unavailable ({type(error).__name__}); next: co rem doctor", file=sys.stderr)
        return {'status': 'unavailable'}
