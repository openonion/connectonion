"""Output-only CLI audit. All providers and caches are isolated.

Run as a module file with --tip-test to grade actual captured output with
llm_do. Without that flag, emit the same output through a pipe for inspection.
No selected model command is ever executed.
"""
import json
import os
import re
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from typer.testing import CliRunner
from typer.main import get_command

from connectonion.cli.main import app
from connectonion.cli.commands import gmail_commands as gm, gdrive_commands as gd


CASES = [
    (['gmail'], 'Read the first listed email', 'co gmail read 1'),
    (['gmail', 'inbox'], 'Read the first listed email', 'co gmail read 1'),
    (['gmail', 'search', 'test'], 'Read the first matching email', 'co gmail read 1'),
    (['gmail', 'read', 'msg-a'], 'Reply with body Thanks', 'co gmail reply msg-a Thanks'),
    (['gmail', 'reply', 'msg-a', 'Thanks'], 'Check sent mail', 'co gmail sent'),
    (['gmail', 'send', 'a@example.invalid', 'Test', 'Hello'], 'Check sent mail', 'co gmail sent'),
    (['gmail', 'sent'], 'Find sent messages to read', 'co gmail search in:sent'),
    (['gmail', 'draft', 'list'], 'Preview the first listed draft', 'co gmail draft preview 1'),
    (['gmail', 'draft', 'create', 'a@example.invalid', 'Test', 'Hello'], 'Attach report.pdf', 'co gmail draft attach draft-a report.pdf'),
    (['gmail', 'draft', 'attach', 'draft-a', 'report.pdf'], 'Preview the staged draft', 'co gmail draft preview draft-a'),
    (['gmail', 'draft', 'remove', 'draft-a', '1'], 'Preview the updated draft', 'co gmail draft preview draft-a'),
    (['gmail', 'draft', 'replace', 'draft-a', '1', 'report.pdf'], 'Preview the updated draft', 'co gmail draft preview draft-a'),
    (['gmail', 'draft', 'preview', 'draft-a'], 'Proceed to the confirmation gate', 'co gmail draft send draft-a'),
    (['gmail', 'draft', 'send', 'draft-a'], 'Inspect the kept draft', 'co gmail draft preview draft-a'),
    (['gdrive'], 'Download the first listed file', 'co gdrive get 1'),
    (['gdrive', 'list'], 'Download the first listed file', 'co gdrive get 1'),
    (['gdrive', 'search', 'Report'], 'Download the first matching file', 'co gdrive get 1'),
    (['gdrive', 'get', 'file-a'], 'Show more files', 'co gdrive list'),
    (['gdrive', 'put', 'report.pdf'], 'Check uploaded files', 'co gdrive list'),
    (['gdrive', 'rm', 'file-a'], 'Show remaining files', 'co gdrive list'),
]


@pytest.mark.parametrize('path', [('gmail',), ('gmail', 'draft'), ('gdrive',)])
def test_help_and_skill_parity(path):
    command = get_command(app)
    for name in path:
        command = command.commands[name]
    visible = {name for name, child in command.commands.items() if not child.hidden}
    skill = (Path(__file__).resolve().parents[2] / 'connectonion/useful_skills/co-mail-and-drive/SKILL.md').read_text()
    documented = set(re.findall(r'co ' + ' '.join(path) + r' ([a-z-]+)', skill))
    result = CliRunner().invoke(app, [*path, '--help'])
    assert result.exit_code == 0
    assert visible == documented
    assert all(re.search(r'\b' + name + r'\b', result.output) for name in visible)


def capture(args, root, failure=None):
    gmail, drive = MagicMock(), MagicMock()
    email = dict(id='msg-a', **{'from': 'a@example.invalid'}, subject='Test',
                 date='Sat, 05 Sep 2026 10:00:00 +0000', unread=False, snippet='Hello')
    gmail.list_inbox.return_value = gmail.list_search.return_value = [email]
    from connectonion.useful_tools.gmail import Gmail
    gmail._format_dicts.side_effect = lambda emails: Gmail._format_dicts(gmail, emails)
    gmail.get_email_body.return_value = 'From: a@example.invalid\n--- Email Body ---\nHello'
    gmail.get_sent_emails.return_value = '1. ID: sent-a, Subject: Test'
    draft = dict(id='draft-a', to='a@example.invalid', subject='Test', body='Hello',
                 attachments=[], attachment_size=0)
    gmail.list_drafts.return_value = [dict(draft, attachments=0)]
    for name in ('create_draft', 'get_draft', 'add_draft_attachment',
                 'remove_draft_attachment', 'replace_draft_attachment'):
        getattr(gmail, name).return_value = draft
    drive.list_files.return_value = drive.search_files.return_value = [
        dict(id='file-a', name='Report.pdf', type='application/pdf', size=5, modified='')]
    drive.download.return_value = 'Downloaded to report.pdf'
    drive.upload.return_value = dict(name='Report.pdf', link='')
    if failure is not None:
        gmail.list_inbox.side_effect = drive.list_files.side_effect = failure
        gmail.send.side_effect = gmail.reply.side_effect = drive.upload.side_effect = failure
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {'GOOGLE_EMAIL': 'sender@example.invalid'}))
        for module, name, value in ((gm, '_gmail', lambda **kw: gmail),
                                    (gd, '_gdrive', lambda: drive),
                                    (gm, 'INBOX_CACHE', root / 'inbox.json'),
                                    (gm, 'DRAFT_CACHE', root / 'drafts.json'),
                                    (gd, 'LIST_CACHE', root / 'drive.json')):
            stack.enter_context(patch.object(module, name, value))
        stack.enter_context(patch.object(gm, 'console', Console(force_terminal=False, width=200)))
        stack.enter_context(patch.object(gd, 'console', Console(force_terminal=False, width=200)))
        stack.enter_context(patch.object(Path, 'is_file', return_value=True))
        return CliRunner().invoke(app, args, input='n\n', prog_name='co')


@pytest.mark.parametrize('args,goal,expected', CASES)
def test_every_command_emits_a_piped_tip(args, goal, expected, tmp_path):
    result = capture(args, tmp_path)
    assert result.exit_code == (1 if args[:3] == ['gmail', 'draft', 'send'] else 0), result.output
    assert 'co ' in result.output.strip().splitlines()[-1]


@pytest.mark.parametrize('surface', ['gmail', 'gdrive'])
def test_provider_error_is_safe_and_actionable(surface, tmp_path):
    from googleapiclient.errors import HttpError
    from httplib2 import Response
    error = HttpError(Response({'status': '403'}), b'PRIVATE_PROVIDER_BODY')
    result = capture([surface], tmp_path, error)
    assert result.exit_code == 1
    assert 'PRIVATE_PROVIDER_BODY' not in result.output
    assert 'HTTP 403' in result.output and 'co auth google' in result.output


@pytest.mark.parametrize('surface', ['gmail', 'gdrive'])
def test_network_error_is_safe_and_actionable(surface, tmp_path):
    result = capture([surface], tmp_path, OSError('PRIVATE_ERROR'))
    assert result.exit_code == 1
    assert 'PRIVATE_ERROR' not in result.output
    assert 'Next: co ' in result.output


@pytest.mark.parametrize('args,next_command', [
    (['gmail', 'send', 'a@example.invalid', 'Test', 'Hello'], 'co gmail sent'),
    (['gmail', 'reply', 'msg-a', 'Thanks'], 'co gmail sent'),
    (['gdrive', 'put', 'report.pdf'], 'co gdrive list'),
])
def test_ambiguous_writes_point_to_inspection(args, next_command, tmp_path):
    result = capture(args, tmp_path, OSError('lost response'))
    assert result.exit_code == 1
    assert 'may have completed' in result.output
    assert result.output.strip().endswith(next_command)


@pytest.mark.parametrize('module,cache,handler,args,method', [
    (gm, 'INBOX_CACHE', gm.handle_gmail_inbox, (), 'list_inbox'),
    (gm, 'INBOX_CACHE', gm.handle_gmail_search, ('missing',), 'list_search'),
    (gd, 'LIST_CACHE', gd.handle_gdrive_list, (), 'list_files'),
    (gd, 'LIST_CACHE', gd.handle_gdrive_search, ('missing',), 'search_files'),
])
def test_empty_listing_cannot_reuse_old_row(module, cache, handler, args, method, tmp_path):
    path = tmp_path / 'cache.json'
    path.write_text(json.dumps({'1': 'old-id'}))
    client = MagicMock()
    getattr(client, method).return_value = []
    with patch.object(module, cache, path), patch.object(module, '_gmail' if module is gm else '_gdrive', return_value=client):
        handler(*args)
        resolved = gm._resolve_email_id(client, '1') if module is gm else gd._resolve_file_id('1')
        assert resolved == ''


@pytest.mark.parametrize('surface,subcommand', [('gmail', 'read'), ('gdrive', 'get')])
def test_usage_error_names_help(surface, subcommand, tmp_path):
    result = capture([surface, subcommand], tmp_path)
    assert result.exit_code == 2
    assert f' {surface} {subcommand} --help' in result.output


if __name__ == '__main__':
    import shlex
    with tempfile.TemporaryDirectory(prefix='google-cli-audit-') as directory:
        for args, goal, expected in CASES:
            result = capture(args, Path(directory))
            if '--tip-test' in sys.argv:
                from connectonion import llm_do
                reply = llm_do(
                    f'You just ran a shell command. Its full output was:\n\n{result.output}\n\n'
                    f'Your goal: {goal}. Reply with ONE shell command and nothing else.',
                    model='co/gemini-3.7-flash',
                ).strip()
                passed = shlex.split(reply) == shlex.split(expected)
                print(json.dumps(dict(command='co ' + ' '.join(args), tip=result.output.strip().splitlines()[-1],
                                      goal=goal, reply=reply, passed=passed)), flush=True)
            else:
                print('COMMAND: co ' + ' '.join(args))
                print(result.output)
