"""Output-only Calendar/YouTube discoverability; no account actions are executed."""
import json
import shlex
import sys
import tempfile
import re
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from rich.text import Text
from rich.console import Console
from typer.testing import CliRunner
from typer.main import get_command
from connectonion.cli.main import app
from connectonion.cli.commands import gcalendar_commands as gc, youtube_commands as yt, creator_commands as rendering

CHANNEL = 'UC' + 'a' * 22
VIDEO = 'abcdefghijk'
CASES = [
    (['gcalendar'], 'Read the first listed event', 'co gcalendar read event-a'),
    (['gcalendar', 'list'], 'Read the first listed event', 'co gcalendar read event-a'),
    (['gcalendar', 'today'], 'List upcoming events', 'co gcalendar list'),
    (['gcalendar', 'read', 'event-a'], 'List upcoming events', 'co gcalendar list'),
    (['gcalendar', 'meetings'], 'List upcoming events', 'co gcalendar list'),
    (['gcalendar', 'free', '2026-09-05'], 'List upcoming events', 'co gcalendar list'),
    (['gcalendar', 'create', 'Demo', '2026-09-05T10:00:00Z', '2026-09-05T11:00:00Z'], 'Review the confirmation options', 'co gcalendar create --help'),
    (['gcalendar', 'meet', 'Demo', '2026-09-05T10:00:00Z', '2026-09-05T11:00:00Z', '--attendees', 'a@example.invalid'], 'Review the confirmation options', 'co gcalendar meet --help'),
    (['gcalendar', 'update', 'event-a', '--title', 'Changed'], 'Review the confirmation options', 'co gcalendar update --help'),
    (['gcalendar', 'delete', 'event-a'], 'Review the confirmation options', 'co gcalendar delete --help'),
    (['youtube'], 'Inspect the first listed video', 'co youtube video 1'),
    (['youtube', 'list'], 'Inspect the first listed video', 'co youtube video 1'),
    (['youtube', 'channel'], 'List this channel', f'co youtube list {CHANNEL}'),
    (['youtube', 'video', VIDEO], 'Inspect its channel', f'co youtube channel {CHANNEL}'),
    (['youtube', 'put', 'clip.mp4', '--title', 'Demo', '--channel', CHANNEL], 'The user approved this exact upload preview; execute that upload', f'co youtube put clip.mp4 --title Demo --channel {CHANNEL} --description \"\" --privacy private --category 22 --confirm synthetic-digest'),
    (['youtube', 'update', VIDEO, '--title', 'Changed'], 'The user approved this exact update preview; execute that update', f'co youtube update {VIDEO} --title Changed --confirm synthetic-digest'),
]

def capture(args, root):
    calendar, youtube = MagicMock(), MagicMock()
    for name in ('list_events', 'get_today_events', 'get_event', 'get_upcoming_meetings', 'find_free_slots'):
        getattr(calendar, name).return_value = 'Event\nID: event-a'
    youtube.list_videos.return_value = [{'id': VIDEO, 'title': 'Demo'}]
    youtube.channel.return_value = {'id': CHANNEL}
    youtube.video.return_value = {'id': VIDEO, 'channel_id': CHANNEL}
    youtube.update.return_value = {'confirmation': 'synthetic-digest'}
    with patch.object(gc, '_client', return_value=calendar), patch.object(yt, '_client', return_value=youtube), \
         patch.object(yt, 'prepare_upload', return_value={'confirmation': 'synthetic-digest', 'file': {'path': 'clip.mp4'}}), \
         patch.object(rendering, '_cache', return_value=root / 'listing.json'), \
         patch.object(rendering, 'console', Console(force_terminal=False, width=240)):
        return CliRunner().invoke(app, args, prog_name='co')

@pytest.mark.parametrize('args,goal,expected', CASES)
def test_piped_tip(args, goal, expected, tmp_path):
    result = capture(args, tmp_path)
    assert result.exit_code == 0, result.output
    assert shlex.split(result.output.strip().splitlines()[-1].split(': ', 1)[-1]) == shlex.split(expected)

def test_youtube_help_skill_parity():
    skill = (Path(__file__).resolve().parents[2] / 'connectonion/useful_skills/co-google/SKILL.md').read_text()
    visible = set(get_command(app).commands['youtube'].commands)
    assert visible == set(re.findall(r'co youtube ([a-z][a-z-]*)', skill))
    assert 'tiktok' not in get_command(app).commands
    for name in visible:
        assert CliRunner().invoke(app, ['youtube', name, '--help']).exit_code == 0

def test_youtube_usage_error_names_help():
    result = CliRunner().invoke(app, ['youtube', 'video'], prog_name='co')
    assert result.exit_code == 2 and 'co youtube video --help' in Text.from_ansi(result.output).plain

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='google-extended-audit-') as directory:
        for args, goal, expected in CASES:
            result = capture(args, Path(directory))
            if '--tip-test' not in sys.argv:
                print(result.output)
                continue
            from connectonion import llm_do
            reply = llm_do(f'You just ran a shell command. Its full output was:\n\n{result.output}\n\n'
                           f'Your goal: {goal}. Reply with ONE shell command and nothing else.',
                           model='co/gemini-3.7-flash').strip()
            print(json.dumps(dict(command='co ' + ' '.join(args), tip=result.output.strip().splitlines()[-1],
                                  goal=goal, reply=reply, passed=shlex.split(reply) == shlex.split(expected))), flush=True)


def test_upload_tip_preserves_quoted_metadata_and_exact_plan(tmp_path):
    clip = tmp_path / "a clip.mp4"
    clip.write_bytes(b"synthetic media")
    with patch.object(yt, '_client', side_effect=AssertionError('preview reached provider')):
        result = CliRunner().invoke(app, ['youtube', 'put', str(clip), '--title', "A 'quoted' demo",
            '--description', 'literal $(no-command)', '--channel', CHANNEL, '--json'])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert shlex.split(data['next_command']) == ['co', 'youtube', 'put', str(clip.resolve()),
        '--title', "A 'quoted' demo", '--channel', CHANNEL, '--description', 'literal $(no-command)',
        '--privacy', 'private', '--category', '22', '--confirm', data['plan']['confirmation']]
    assert 'After the user approves' in data['next_tip']


def test_update_tip_preserves_explicit_empty_description(tmp_path):
    result = capture(['youtube', 'update', VIDEO, '--description', '', '--json'], tmp_path)
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert shlex.split(data['next_command']) == ['co', 'youtube', 'update', VIDEO,
        '--description', '', '--confirm', 'synthetic-digest']
    assert 'After the user approves' in data['next_tip']
