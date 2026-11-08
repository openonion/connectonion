"""The REM sandbox profile keeps a dispatched Codex from reading the owner's credentials.

Names are fictional; every home here is a temp tree, never the operator's.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from connectonion.rem import sandbox_profile as sp

ON_MAC = sys.platform == 'darwin' and Path('/usr/bin/sandbox-exec').exists()
mac_only = pytest.mark.skipif(not ON_MAC, reason='sandbox-exec exists only on macOS; '
                              'Linux runs are unprotected and say so via protected=False')

DIRS = ['.co', '.ssh', '.config/gh', '.aws', '.gnupg', 'Library/Keychains', '.docker', '.kube',
        '.config/gcloud', '.azure', '.claude']
FILES = ['.netrc', '.git-credentials', '.npmrc', '.pypirc']


def fake_home(tmp_path):
    home = tmp_path / 'home-of-wren'
    for name in DIRS:
        (home / name).mkdir(parents=True)
        (home / name / 'canary').write_text('canary-for-wren\n')
    for name in FILES:
        (home / name).write_text('canary-for-wren\n')
    (home / '.co' / 'tasks' / 'task-7').mkdir(parents=True)
    (home / '.co' / 'tasks' / 'task-7' / 'brief.md').write_text('brief\n')
    (home / '.codex').mkdir()
    (home / '.codex' / 'auth.json').write_text('{}\n')
    (home / 'notes.txt').write_text('ordinary\n')
    return home


def canaries(home):
    return [home / name / 'canary' for name in DIRS] + [home / name for name in FILES]


def test_every_credential_location_is_denied_by_its_real_path(tmp_path):
    real = tmp_path / 'real-home'
    real.mkdir()
    link = tmp_path / 'linked-home'
    link.symlink_to(real)
    text = sp.profile(link)
    real = os.path.realpath(real)
    assert text.startswith('(version 1)\n(allow default)')
    for name in DIRS:
        assert f'(subpath "{real}/{name}")' in text
    for name in FILES:
        assert f'(literal "{real}/{name}")' in text
    assert f'{real}/.codex' not in text
    assert str(link) not in text


def test_each_credential_path_is_resolved_on_its_own(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    elsewhere = tmp_path / 'vault'
    elsewhere.mkdir()
    (home / '.ssh').symlink_to(elsewhere)
    assert f'(subpath "{os.path.realpath(elsewhere)}")' in sp.profile(home)


def test_allowed_co_subpaths_come_after_the_deny_and_must_stay_inside_co(tmp_path):
    home = tmp_path / 'home'
    task = home / '.co' / 'tasks' / 'task-7'
    text = sp.profile(home, allow_co=[task])
    co = os.path.realpath(home / '.co')
    deny = text.index(f'(subpath "{co}")')
    allow = text.index(f'(allow file-read* file-write* (subpath "{co}/tasks/task-7"))')
    assert deny < allow
    with pytest.raises(ValueError, match='inside'):
        sp.profile(home, allow_co=[home / '.ssh'])
    with pytest.raises(ValueError, match='inside'):
        sp.profile(home, allow_co=[home / '.co'])


def test_quotes_and_backslashes_are_escaped_and_control_characters_refused(tmp_path):
    odd = tmp_path / 'wren "the" \\ worktree'
    text = sp.profile(tmp_path, deny=[odd])
    assert '(subpath "' + os.path.realpath(odd).replace('\\', '\\\\').replace('"', '\\"') + '")' in text
    with pytest.raises(ValueError, match='control'):
        sp.profile(tmp_path, deny=[tmp_path / 'a\nb'])


def test_writable_confines_writes_to_the_roots_given(tmp_path):
    work = tmp_path / 'work'
    text = sp.profile(tmp_path, writable=[work])
    assert '(deny file-write*)' in text
    assert f'(subpath "{os.path.realpath(work)}")' in text.split('(deny file-write*)')[1]
    assert '(deny file-write*)' not in sp.profile(tmp_path)


def test_linux_returns_argv_unchanged_and_says_it_is_unprotected(monkeypatch, tmp_path):
    monkeypatch.setattr(sp.sys, 'platform', 'linux')
    argv, protected = sp.wrap(['codex', 'exec', 'hi'], home=tmp_path)
    assert argv == ['codex', 'exec', 'hi']
    assert protected is False
    assert sp.prefix(home=tmp_path) == ([], False)


def test_mac_prefix_is_sandbox_exec_with_the_profile(monkeypatch, tmp_path):
    monkeypatch.setattr(sp.sys, 'platform', 'darwin')
    argv, protected = sp.wrap(['codex', 'exec'], home=tmp_path)
    assert protected is True
    assert argv[:2] == ['/usr/bin/sandbox-exec', '-p']
    assert argv[2] == sp.profile(tmp_path)
    assert argv[3:] == ['codex', 'exec']


def _cat(path, profile=None):
    prefix = [] if profile is None else ['/usr/bin/sandbox-exec', '-p', profile]
    return subprocess.run([*prefix, '/bin/cat', str(path)], capture_output=True, text=True).returncode


@mac_only
def test_without_the_profile_every_canary_is_readable(tmp_path):
    """The red half: the fake home really does leak when nothing guards it."""
    home = fake_home(tmp_path)
    assert [_cat(path) for path in canaries(home)] == [0] * len(canaries(home))


@mac_only
def test_the_profile_denies_every_canary_and_keeps_codex_auth_readable(tmp_path):
    home = fake_home(tmp_path)
    other = tmp_path / 'other-worktree'
    other.mkdir()
    (other / 'secret.txt').write_text('x\n')
    task = home / '.co' / 'tasks' / 'task-7'
    profile = sp.profile(home, allow_co=[task], deny=[other])
    denied = {str(path): _cat(path, profile) for path in [*canaries(home), other / 'secret.txt']}
    assert all(code != 0 for code in denied.values()), denied
    assert _cat(home / '.codex' / 'auth.json', profile) == 0
    assert _cat(home / 'notes.txt', profile) == 0
    assert _cat(task / 'brief.md', profile) == 0
    assert _cat(home / '.co' / 'tasks' / 'other-task', profile) != 0


@mac_only
def test_writable_blocks_writes_elsewhere_and_allows_the_workspace(tmp_path):
    home = fake_home(tmp_path)
    work = tmp_path / 'work'
    work.mkdir()
    profile = sp.profile(home, writable=[work])

    def touch(path):
        return subprocess.run(['/usr/bin/sandbox-exec', '-p', profile, '/usr/bin/touch', str(path)],
                              capture_output=True).returncode
    # The fake home sits under the temp roots Codex may write, so the denials proven here are
    # the ones layered above them; a write outside every root is shown on the real path.
    assert touch(work / 'ok') == 0
    assert touch(home / '.ssh' / 'planted') != 0
    assert touch(home / '.codex' / 'config.toml') != 0
    assert touch(home / '.codex' / 'sessions-file') != 0
    (home / '.codex' / 'sessions').mkdir()
    assert touch(home / '.codex' / 'sessions' / 'rollout.jsonl') == 0
    assert touch(home / '.codex' / 'state_5.sqlite-wal') == 0
