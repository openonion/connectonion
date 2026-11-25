"""和 Codex 聊这件事: a real conversation with the agent about an item, turn by turn, resumed by its session."""
import json
import time

import pytest

from connectonion.rem import conversations
from connectonion.rem.files import Notebook, RemError
from tests.unit.test_rem_tasks import (_codex_requests, _waiting_row, fake_claude, fake_codex,  # noqa: F401
                                       task_notebook)


def _answered(root, talk_id, turns):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        talk = conversations.read(root, talk_id)
        if talk['state'] == 'idle' and len(talk['turns']) >= turns:
            return talk
        time.sleep(.05)
    raise AssertionError(talk)


def test_talking_about_a_waiting_item_seeds_it_answers_and_the_next_turn_resumes_the_session(task_notebook, fake_codex):
    row = _waiting_row(task_notebook)
    talk = conversations.begin(task_notebook, 'codex', key=row['keys'][0])
    assert talk['state'] == 'working' and talk['about'] == {'key': row['key']}
    seed = talk['turns'][0]
    assert seed['role'] == 'context' and 'Fernhill Labs contract draft' in seed['text'] and 'projects/pilot.md' in seed['text']
    talk = _answered(task_notebook, talk['id'], 2)
    assert talk['turns'][1]['role'] == 'agent' and talk['turns'][1]['text'] and talk['session_id']
    assert conversations.begin(task_notebook, 'codex', key=row['key'])['id'] == talk['id']   # opened again: the same one
    conversations.say(task_notebook, talk['id'], 'Draft the follow-up to Fern, short.')
    talk = _answered(task_notebook, talk['id'], 4)
    assert [turn['role'] for turn in talk['turns']] == ['context', 'agent', 'owner', 'agent']
    requests = _codex_requests(fake_codex)
    assert requests['thread/resume']['threadId'] == talk['session_id']
    assert requests['turn/start']['input'][0]['text'] == 'Draft the follow-up to Fern, short.'


def test_an_archived_claude_session_goes_on_in_its_own_folder_with_its_own_id(task_notebook, fake_claude, tmp_path):
    folder = tmp_path / 'fernhill'
    folder.mkdir()
    Notebook(task_notebook).write('sessions/2026-11-08-fernhill.md', (
        '# Fernhill Labs contract\n\n## Facts\n- Agent: Claude Code\n- Session: 7d2c4b1e-0f3a-4c5d-9e8f-1a2b3c4d5e6f\n'
        f'- Folder: {folder}\n\n## Final reply\n> Drafted the contract outline.\n'))
    talk = conversations.begin(task_notebook, session='sessions/2026-11-08-fernhill.md')
    assert talk['agent'] == 'claude' and talk['session_id'] == '7d2c4b1e-0f3a-4c5d-9e8f-1a2b3c4d5e6f' and talk['cwd'] == str(folder)
    assert talk['state'] == 'idle' and talk['turns'] == []          # nothing is sent until the owner writes
    conversations.say(task_notebook, talk['id'], 'Where did we leave the indemnity clause?')
    talk = _answered(task_notebook, talk['id'], 2)
    assert talk['turns'][-1]['role'] == 'agent', talk.get('reason')
    assert (folder / 'claude-was-here.md').exists()


def test_a_message_waits_for_the_answer_and_unknown_items_are_refused(task_notebook):
    with pytest.raises(RemError, match='no longer open'):
        conversations.begin(task_notebook, 'codex', key='people/nobody.md\nNothing.')
    with pytest.raises(RemError, match='conversation id'):
        conversations.read(task_notebook, '../tasks')
    with pytest.raises(RemError, match='session page'):
        conversations.begin(task_notebook, session='projects/pilot.md')
