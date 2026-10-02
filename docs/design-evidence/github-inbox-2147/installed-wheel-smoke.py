import json, os, subprocess, sys, tempfile
from pathlib import Path
from connectonion.inbox.github import GitHub
from connectonion.inbox.store import Inbox
import connectonion.inbox.github as installed
assert Path(installed.__file__).resolve().is_relative_to(Path(os.environ['PYTHONPATH']).resolve())
with tempfile.TemporaryDirectory(prefix='co-github-wheel-') as home:
    os.environ['CO_INBOX_HOME'] = home
    def co(*args):
        run = subprocess.run([sys.executable, '-m', 'connectonion.cli.main', 'github', *args], text=True, capture_output=True, timeout=30)
        assert run.returncode == 0, run.stderr
        return run.stdout
    co('watch', 'acme/app')
    box = Inbox('github')
    bot = GitHub()
    row = {'id':1,'number':1,'title':'Wheel task','body':'Original **markdown**','state':'open','labels':[],
           'user':{'login':'alice'},'created_at':'2026-10-02T10:01:00Z','updated_at':'2026-10-02T10:01:00Z',
           'html_url':'https://github.com/acme/app/issues/1'}
    bot.pages = lambda path, **kwargs: [row] if path.endswith('/issues') else []
    bot.scan(box, since='2026-10-02T10:00:00Z', now='2026-10-02T10:02:00Z')
    message = json.loads(co('receive', '--timeout', '0'))
    assert message['event']['repo'] == 'acme/app'
    co('done', message['id'])
    assert not box.unread()
    row['id'] = 2
    row['number'] = 2
    bot.scan(box, since='2026-10-02T10:00:00Z', now='2026-10-02T10:03:00Z')
    assert box.hold_lock()
    reply = json.loads(co('consume', '--once', '--no-reply', 'cat'))
    assert reply['event']['number'] == 2
    box.release_lock()
    assert not box.unread()
    assert not box.sent.exists() or not box.sent.read_text().strip()
    print('Installed wheel: watch → fixture scan → receive → done; consume --once cat completes locally, no sent records')
