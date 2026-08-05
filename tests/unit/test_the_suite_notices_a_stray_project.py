"""A `.co/` in a shared parent silently becomes every test's project.

`_never_touch_the_real_home` isolates HOME, so `~/.co` is covered. This is the
other half: `project_root()` walks up from the *working directory*, and a stray
`.co/` anywhere above it wins.

Measured (#694). My real-host verification runs left a `/private/tmp/.co/`
behind. Afterwards a unit test with nothing to do with any of that failed:

    assert logger.log_file_path == Path(".co/logs/test-agent.log").resolve()
    E  assert PosixPath('/private/tmp/.co/logs/test-agent.log')
           == PosixPath('/…/wt-695/.co/logs/test-agent.log')

standalone, not only in a particular order — so `-p no:randomly` does not hide
this one. And it is invisible on CI, where the machine is clean, which is the
worst property to have: a local run disagrees with CI for a reason nobody can
reproduce.

The escape reproduces exactly:

    cwd          /private/tmp/probe_no_co     (no .co of its own)
    project_root /private/tmp                 (the stray one wins)

The guard in conftest does not repoint anything — tests that chdir into their
own project depend on the walk-up finding it, and pinning the answer would
break them. It refuses to let the walk-up escape somewhere shared, so
contamination becomes a failure with a name instead of a wrong answer.
"""

import os
from pathlib import Path

import pytest


class TestTheWalkUpCanEscape:
    """What the guard is for, demonstrated without needing a stray directory
    in a real shared location."""

    def test_a_parent_owning_co_becomes_the_project(self, tmp_path, monkeypatch):
        from connectonion.project import project_root

        (tmp_path / ".co").mkdir()
        deep = tmp_path / "somewhere" / "deeper"
        deep.mkdir(parents=True)
        monkeypatch.chdir(deep)

        assert project_root() == tmp_path.resolve()

    def test_without_one_it_stops_at_the_start(self, tmp_path, monkeypatch):
        from connectonion.project import project_root

        deep = tmp_path / "no" / "co" / "anywhere"
        deep.mkdir(parents=True)
        monkeypatch.chdir(deep)

        assert project_root() == deep.resolve()


class TestTheGuardItself:

    def _check(self, resolved: Path, tmp_root: Path, repo: Path) -> bool:
        """The condition conftest applies, so it is tested rather than trusted."""
        return (resolved == repo or resolved.is_relative_to(tmp_root)
                or resolved.is_relative_to(repo))

    def test_the_repo_is_allowed(self, tmp_path):
        repo = Path(__file__).resolve().parents[2]

        assert self._check(repo, tmp_path, repo)

    def test_a_test_s_own_tmp_dir_is_allowed(self, tmp_path):
        repo = Path(__file__).resolve().parents[2]
        mine = tmp_path / "project"
        mine.mkdir()

        assert self._check(mine, tmp_path, repo)

    def test_a_shared_parent_is_not(self, tmp_path):
        """The measured case: /private/tmp owning a .co."""
        repo = Path(__file__).resolve().parents[2]

        assert not self._check(Path("/private/tmp"), tmp_path, repo)

    def test_the_operators_home_is_not(self, tmp_path):
        repo = Path(__file__).resolve().parents[2]

        assert not self._check(Path.home(), tmp_path, repo)


class TestTheGuardIsInstalled:
    """It is autouse in conftest, so it runs for every test including this one."""

    def test_conftest_carries_it(self):
        import inspect
        import tests.conftest as conftest

        source = inspect.getsource(conftest)

        assert "_no_stray_project_above_the_test" in source
        assert "autouse=True" in source
