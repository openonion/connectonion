#!/usr/bin/env python3
"""`codex app-server` as the real one answers, replayed from a recorded turn.

codex_app_server_turn.jsonl is a real codex-cli 0.167 turn ("add one line to
README.md"), with paths and account details made fictional. This script answers
the same JSON-RPC requests in the same shapes and does the turn's work on disk:
it writes `codex-was-here.md` in the turn's cwd and, when the prompt names a
`Deliverable: <path>`, a result there, with pid.txt, env.json (the names of its
environment) and tmpdir.txt beside it. Like the real app-server it exits when
its client goes away (stdin closes), even mid-turn.

Environment (inherited, as the real app-server inherits it):
  FAKE_CODEX_RECORD   append every request as one JSON line to this file
  FAKE_CODEX_SLEEP    seconds to wait after turn/start before the turn's notifications
  FAKE_CODEX_MISSING  do not write the deliverable
  FAKE_CODEX_STATUS   the turn/completed status (default: the recorded "completed")
  FAKE_CODEX_PLANT    replace cwd/.git with a repository whose config runs a command
"""
import json
import os
import pathlib
import re
import select
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
RECORDED = [json.loads(line) for line in (HERE / 'codex_app_server_turn.jsonl').read_text().splitlines()]
RESPONSES = {message['id']: message['result'] for message in RECORDED if 'id' in message and 'method' not in message}
BY_METHOD = {'initialize': RESPONSES[1], 'account/read': RESPONSES[2], 'thread/start': RESPONSES[3],
             'turn/start': RESPONSES[4]}
TURN = [message for message in RECORDED if message.get('method') and message['method'] != 'thread/started']


def send(message):
    sys.stdout.write(json.dumps(message) + '\n')
    sys.stdout.flush()


def work(params):
    text = ''.join(part.get('text', '') for part in params.get('input', []))
    pathlib.Path(params['cwd'], 'codex-was-here.md').write_text('Pilot notes\n')
    if os.environ.get('FAKE_CODEX_PLANT') and pathlib.Path(params['cwd'], '.git').is_file():
        git = pathlib.Path(params['cwd'], '.git')
        git.unlink()
        git.mkdir()
        (git / 'config').write_text('[core]\n\tfsmonitor = touch planted\n')
    found = re.search(r'Deliverable: (\S+)', text)
    if not found:
        return
    deliverable = pathlib.Path(found.group(1))
    (deliverable.parent / 'pid.txt').write_text(str(os.getpid()))
    (deliverable.parent / 'env.json').write_text(json.dumps(sorted(os.environ)))
    (deliverable.parent / 'tmpdir.txt').write_text(os.environ.get('TMPDIR', ''))
    if not os.environ.get('FAKE_CODEX_MISSING'):
        deliverable.write_text('# Pilot review\nReady for owner review.\n')


def wait(seconds):
    """The turn's running time. Like the real server, keep answering other requests
    meanwhile, and leave when the client closes stdin."""
    deadline = time.monotonic() + seconds
    while (left := deadline - time.monotonic()) > 0:
        if select.select([sys.stdin], [], [], left)[0]:
            line = sys.stdin.readline()
            if not line:
                sys.exit(0)
            handle(line)


def notifications():
    status = os.environ.get('FAKE_CODEX_STATUS')
    for message in TURN:
        if status and message['method'] == 'turn/completed':
            message = json.loads(json.dumps(message))
            message['params']['turn']['status'] = status
        yield message


def handle(line):
    request = json.loads(line)
    if 'id' not in request:
        return
    if os.environ.get('FAKE_CODEX_RECORD'):
        with open(os.environ['FAKE_CODEX_RECORD'], 'a') as record:
            record.write(json.dumps({'method': request['method'], 'params': request.get('params')}) + '\n')
    if request['method'] != 'turn/start':
        send({'id': request['id'], 'result': BY_METHOD.get(request['method'], {})})
        return
    work(request['params'])
    send({'id': request['id'], 'result': BY_METHOD['turn/start']})
    wait(float(os.environ.get('FAKE_CODEX_SLEEP') or 0))
    for message in notifications():
        send(message)


while line := sys.stdin.readline():
    handle(line)
