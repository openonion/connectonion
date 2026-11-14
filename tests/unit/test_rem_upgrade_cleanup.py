"""The upgrade fixture owns its whole temporary home, including an unrecorded replacement."""

from contextlib import contextmanager

import pytest

from tests.e2e.cli import test_rem_open_after_upgrade as upgrade


def test_replacement_lock_is_held_until_cleanup_finishes(tmp_path):
    fcntl = pytest.importorskip('fcntl')
    with upgrade._wait_for_replacement(tmp_path):
        with (tmp_path / 'owner-invite.lock').open('a+b') as other:
            with pytest.raises(BlockingIOError):
                fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    with (tmp_path / 'owner-invite.lock').open('a+b') as other:
        fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_cleanup_finds_an_unrecorded_host_only_in_its_own_home(tmp_path, monkeypatch):
    home, other = tmp_path / 'home', tmp_path / 'other'
    stopped, locked = [], []

    @contextmanager
    def lock(directory):
        locked.append(directory)
        yield
        locked.pop()

    monkeypatch.setattr(upgrade, '_wait_for_replacement', lock)
    monkeypatch.setattr(upgrade.host_leak_guard, 'hosts_under', lambda root: [
        (42, str(home), 'our test'), (43, str(other), 'another test')])

    def stop(root, pid):
        assert locked == [home / '.co']
        stopped.append((root, pid))

    monkeypatch.setattr(upgrade.host_leak_guard, 'stop', stop)
    upgrade._stop_upgraded_hosts(tmp_path, home)
    assert stopped == [(tmp_path, 42)]
