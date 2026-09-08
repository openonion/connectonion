"""Pinned text-only discovery: never execute a model's chosen command."""
from contextlib import ExitStack
import json
from pathlib import Path
import shlex
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.commands import gmail_commands as gm

CASES = [
    (['mark','message-a','--read'], 'Read the updated message as JSON', 'co gmail read message-a --json'),
    (['mark','message-a','--unread'], 'Read the updated message as JSON', 'co gmail read message-a --json'),
    (['archive','message-a'], 'Read the updated message as JSON', 'co gmail read message-a --json'),
    (['star','message-a'], 'Read the updated message as JSON', 'co gmail read message-a --json'),
    (['star','message-a','--remove'], 'Read the updated message as JSON', 'co gmail read message-a --json'),
    (['label','list'], 'Learn the label-add syntax', 'co gmail label add --help'),
    (['label','add','message-a','Projects'], 'Read the updated message as JSON', 'co gmail read message-a --json'),
    (['label','remove','message-a','Projects'], 'Read the updated message as JSON', 'co gmail read message-a --json'),
    (['attachments','message-a'], 'Download all listed attachments to /tmp', 'co gmail download message-a --all --to /tmp'),
    (['download','message-a','--all','--to','/tmp'], 'Inspect the message attachment list as JSON', 'co gmail attachments message-a --json'),
    (['unanswered'], 'Read the first listed email', 'co gmail read message-a'),
    (['mark','message-a','--json'], 'Learn the required mark flags', 'co gmail mark --help'),
]


def capture(args, directory):
    client = MagicMock()
    client.get_account_email.return_value = 'me@example.invalid'
    client._credentials.scopes = {'gmail.modify'}
    for name in ['mark_read','mark_unread','archive_email','star_email','unstar_email','add_label','remove_label']:
        getattr(client,name).return_value = 'Message updated: message-a'
    client._get_service().users().labels().list().execute.return_value = {'labels':[{'id':'Label_a', 'name':'Projects'}]}
    client.list_attachments.return_value = [{'id':'attachment-a', 'filename':'report.txt','size':5,'mime_type':'text/plain','inline':False}]
    client.download_attachments.return_value = {'items':[{'id':'attachment-a','status':'saved','path':'/tmp/report.txt'}],'complete':True}
    client.list_unanswered.return_value = {'items':[{'id':'message-a','from':'other@example.invalid'}], 'complete':True,'truncated':False,'next_cursor':None}
    with ExitStack() as stack:
        stack.enter_context(patch.object(gm, '_gmail', return_value=client))
        stack.enter_context(patch.object(gm, 'INBOX_CACHE', directory/'legacy.json'))
        return CliRunner().invoke(app, ['gmail', *args])


@pytest.mark.parametrize('args,goal,expected', CASES)
def test_piped_next_command_is_present(args, goal, expected, tmp_path):
    result = capture(args, tmp_path)
    assert result.exit_code == (2 if args == ['mark','message-a','--json'] else 0)
    if '--json' in args:
        assert json.loads(result.stdout)['next_command'] == expected
    elif args[0] == 'attachments':
        assert 'co gmail download message-a --all --to <directory>' in result.stderr
    else:
        assert expected in result.stderr


if __name__ == '__main__':
    from connectonion import llm_do
    with tempfile.TemporaryDirectory(prefix='gmail-mailbox-tip-') as directory:
        for args, goal, expected in CASES:
            result = capture(args, Path(directory))
            reply = llm_do(f'You ran a shell command. Its full output was:\n{result.output}\n'
                f'Goal: {goal}. Reply with ONE shell command and nothing else.', model='co/gemini-3.7-flash').strip()
            print(json.dumps({'command':'co gmail '+' '.join(args), 'goal':goal,
                'expected':expected, 'reply':reply, 'passed':shlex.split(reply)==shlex.split(expected)}), flush=True)
