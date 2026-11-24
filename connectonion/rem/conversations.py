"""和 Codex 聊这件事: the owner talks with Codex or Claude Code about one open item, or goes on
with an archived session, inside the live reader.

Each turn is one run of the agent through co ai's harness, the same native runner a task
uses, resumed by the agent's own session id: the agent keeps the whole conversation, REM
keeps the transcript the page shows. A turn runs in a detached worker; the page polls.
The owner never copies a command (D-60).
"""

import argparse
import math
import re
import subprocess
import sys
from pathlib import Path

from .files import Notebook, RemError, read_json, state_path, write_json
from .service import now
from .tasks import FULL_ACCESS, HARNESSES, _agent, _lock, identity

# An archived session's agent, in the session page's words (sessions.AGENTS), as a task agent.
SESSION_AGENTS = {'Codex': 'codex', 'Claude Code': 'claude'}


def _folder(root, talk_id):
    if not re.fullmatch(r'[a-f0-9]{32}', talk_id):
        raise RemError('Use a conversation id the reader gave you')
    return state_path(Path(root), f'talks/{talk_id}')


def _about_item(root, row, folder):
    from .tasks import _project_dir
    project = _project_dir(root, {'record': row['record']})
    seed = (f"The owner wants to talk with you about an open item in his notebook (REM, at {Path(root).resolve()}).\n"
            f"Notebook page: {row['record']}\nItem: {row['text']}\n"
            + (f"Project folder, to read: {project}\n" if project else '') +
            f"Your work folder: {folder / 'work'}\n"
            'Read the page for context. Help him think it through and prepare work when he asks. '
            'Never push, merge, send mail or post: those stay his click.\n'
            'Start with two or three sentences: what you understand the item to be, and what you could do next.')
    return {'title': row['text'], 'about': {'key': row['key']}, 'cwd': str(folder / 'work'), 'session_id': '', 'seed': seed}


def _about_session(root, record, folder):
    if not record.startswith('sessions/'):
        raise RemError('Only an agent session page can be continued')
    text = Notebook(root).read(record)
    facts = dict(re.findall(r'^- ([A-Za-z ]+): (.*)$', text, re.M))
    agent, session_id = SESSION_AGENTS.get(facts.get('Agent', '')), facts.get('Session', '').strip()
    if not agent or not session_id:
        raise RemError('This session page does not name a Codex or Claude Code session to continue')
    place = Path(facts.get('Folder', '')).expanduser()
    # The agent finds its own session from the folder it ran in, as `codex resume` would.
    cwd = str(place) if place.is_absolute() and place.is_dir() else str(folder / 'work')
    title = re.search(r'^# (.+)$', text, re.M)
    return {'title': title[1] if title else record, 'about': {'session': record}, 'cwd': cwd,
            'session_id': session_id, 'seed': ''}, agent


def begin(root, agent='codex', *, key=None, session=None):
    """Open the conversation about an item (key) or a session page (session), once; the first
    turn starts at once. Opening it again returns the same conversation."""
    if session:
        folder = _folder(root, identity(f'session\n{session}'))
        about, agent = _about_session(root, session, folder)
    else:
        from .tasks import unfinished
        row = unfinished(root, key)
        folder = _folder(root, identity(f"talk\n{_agent(agent)}\n{row['key']}"))
        about = _about_item(root, row, folder)
    with _lock(folder):
        if saved := read_json(folder / 'talk.json', {}):
            return saved
        (folder / 'work').mkdir(exist_ok=True, mode=0o700)
        seed = about.pop('seed')
        talk = {'id': folder.name, 'agent': agent, **about, 'state': 'idle', 'turns': []}
        if seed:
            talk['turns'].append({'role': 'context', 'text': seed, 'at': now().isoformat()})
            talk = _spawn(root, folder, talk)
        write_json(folder / 'talk.json', talk)
        return talk


def say(root, talk_id, text):
    """The owner's next message: sent to the same agent session as one more turn."""
    if not isinstance(text, str) or not text.strip():
        raise RemError('Write a message first')
    folder = _folder(root, talk_id)
    with _lock(folder):
        talk = _current(folder)
        if talk['state'] == 'working':
            raise RemError(f"{talk['agent'].capitalize()} is still answering; send this when it has")
        talk['turns'].append({'role': 'owner', 'text': text.strip(), 'at': now().isoformat()})
        talk = _spawn(root, folder, talk)
        write_json(folder / 'talk.json', talk)
        return talk


def read(root, talk_id):
    folder = _folder(root, talk_id)
    with _lock(folder):
        return _current(folder)


def _current(folder):
    """The saved conversation; a turn whose worker is gone ends with that said."""
    from .live_host import _alive
    talk = read_json(folder / 'talk.json', {})
    if not talk:
        raise RemError('No such conversation; open it again from its item')
    if talk['state'] == 'working' and not _alive(talk):
        talk.update(state='idle', reason='The agent stopped before it answered; send the message again')
        write_json(folder / 'talk.json', talk)
    return talk


def _spawn(root, folder, talk):
    from .runner import child_env
    command = [sys.executable, '-m', 'connectonion.rem.conversations', '--root', str(Path(root).resolve()), '--id', talk['id']]
    with (folder / 'worker.log').open('ab') as output:
        process = subprocess.Popen(command, cwd=folder, env=child_env(), stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    return {**talk, 'state': 'working', 'reason': '', 'pid': process.pid, 'command': ' '.join(command[1:])}


def turn(root, talk_id):
    """The worker: the last message goes to the agent's session, and its answer joins the transcript."""
    from ..cli.co_ai import harness
    from .config import read_config
    from .inquiry import stage_config
    folder = _folder(root, talk_id)
    talk = read(root, talk_id)
    config = stage_config(root, read_config(root), 'task')
    model = config['model'] if talk['agent'] == 'codex' and config['model'] != 'default' else ''
    answer = harness.run(HARNESSES[talk['agent']], talk['turns'][-1]['text'], model, cwd=talk['cwd'],
                         timeout=math.ceil(config['limits']['timeout_seconds']), effort=config['effort'],
                         session_id=talk['session_id'], add_dirs=(str(folder),), user_setup=True, **FULL_ACCESS)
    with _lock(folder):
        talk = read_json(folder / 'talk.json', {})
        if answer['result']:
            talk['turns'].append({'role': 'agent', 'text': answer['result'], 'at': now().isoformat()})
        talk.update(state='idle', session_id=answer.get('session_id') or talk['session_id'],
                    reason='' if answer['result'] else answer['error'] or 'The agent ended without an answer')
        write_json(folder / 'talk.json', talk)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--id', required=True)
    args = parser.parse_args()
    turn(args.root, args.id)
