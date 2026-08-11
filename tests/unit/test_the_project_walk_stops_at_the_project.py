"""`project_root()` climbed out of the project and kept going.

The walk looks for the nearest `.co/` above the working directory and has no
upper bound, so it does not stop at anything that means "you have left the
project" — not the repository, not `$HOME`, not the filesystem root. The module
docstring already records what that costs:

    Two of those bugs failed open: a project configured ``trust: strict`` ran as
    ``careful``, and an address on the blocklist read back as a stranger.

It notes that a stray `.co/` shadows the project's own. What it does not say is
that on any ordinary machine there is always one, because `~/.co` — the *global*
config directory, holding keys and machine defaults — sits directly above every
directory the user owns. Measured before this change:

    ~/Desktop   ->  /Users/me       (that is $HOME, via the global ~/.co)
    /tmp        ->  /private/tmp    (a stray .co/ any user on the box can create)

So `co` run anywhere under `$HOME` that is not inside a project believes it is in
a project rooted at `$HOME`, and reads the global `~/.co` as that project's
config — trust lists included. The failure is silent and it fails open.

Two boundaries, both meaning "the project cannot be above here":

- a directory holding `.git` — a `.co/` reached by climbing out of the
  repository belongs to something else
- `$HOME` — and `$HOME/.co` is the global config, never a project's own

What is deliberately *not* changed: the global `~/.co` stays reachable for the
things that are genuinely global. `project_identity()` already falls back to
`address.load(Path.home() / CO_DIR)` by name, and must keep working. The bug is
not that `~/.co` gets read; it is that it gets read *as a particular project's
configuration* by anyone standing in the wrong directory.
"""

from pathlib import Path

import pytest

from connectonion.project import project_root


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A machine whose $HOME has the usual global ~/.co."""
    fake_home = tmp_path / "home"
    (fake_home / ".co").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    return fake_home


class TestTheGlobalConfigIsNotAProject:
    """`~/.co` holds keys and defaults for the machine, not for a project."""

    def test_a_plain_directory_under_home_is_not_the_home_project(self, home, monkeypatch):
        desktop = home / "Desktop"
        desktop.mkdir()
        monkeypatch.chdir(desktop)

        assert project_root() != home, (
            "standing in ~/Desktop resolved the project to $HOME, so the global "
            "~/.co — keys, trust defaults — is now read as this project's config"
        )

    def test_it_resolves_to_where_you_are(self, home, monkeypatch):
        desktop = home / "Desktop"
        desktop.mkdir()
        monkeypatch.chdir(desktop)

        assert project_root() == desktop

    def test_home_itself_is_not_a_project(self, home, monkeypatch):
        monkeypatch.chdir(home)

        assert project_root() == home, "cwd is still the fallback"
        # …but not because ~/.co made it one: the same answer with no ~/.co.


class TestTheRepositoryIsABoundary:

    def test_a_co_above_the_repo_is_not_this_repos_project(self, tmp_path, monkeypatch):
        """A git worktree has no `.co/`; the walk used to leave the checkout."""
        (tmp_path / ".co").mkdir()                 # stray, above everything
        repo = tmp_path / "checkout"
        (repo / ".git").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "elsewhere"))
        monkeypatch.chdir(repo)

        assert project_root() != tmp_path, (
            f"walked out of the repository at {repo} and took the .co/ above it"
        )
        assert project_root() == repo

    def test_a_subdirectory_of_the_repo_stops_at_the_repo(self, tmp_path, monkeypatch):
        (tmp_path / ".co").mkdir()
        repo = tmp_path / "checkout"
        (repo / ".git").mkdir(parents=True)
        deep = repo / "src" / "pkg"
        deep.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "elsewhere"))
        monkeypatch.chdir(deep)

        assert project_root() == deep, "no .co/ inside the repo, so files live here"

    def test_a_worktree_git_file_is_a_boundary_too(self, tmp_path, monkeypatch):
        """In a worktree `.git` is a file, not a directory."""
        (tmp_path / ".co").mkdir()
        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: /somewhere/.git/worktrees/wt\n")
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "elsewhere"))
        monkeypatch.chdir(worktree)

        assert project_root() != tmp_path
        assert project_root() == worktree


class TestARealProjectStillResolves:
    """The whole point of the walk, which must keep working."""

    def test_a_subdirectory_finds_its_project(self, home, monkeypatch):
        project = home / "work" / "agent"
        (project / ".co").mkdir(parents=True)
        deep = project / "src" / "tools"
        deep.mkdir(parents=True)
        monkeypatch.chdir(deep)

        assert project_root() == project

    def test_the_project_wins_over_the_global_config(self, home, monkeypatch):
        project = home / "work" / "agent"
        (project / ".co").mkdir(parents=True)
        monkeypatch.chdir(project)

        assert project_root() == project

    def test_a_project_inside_a_repo_is_found(self, tmp_path, monkeypatch):
        repo = tmp_path / "checkout"
        (repo / ".git").mkdir(parents=True)
        project = repo / "agents" / "mine"
        (project / ".co").mkdir(parents=True)
        deep = project / "sub"
        deep.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "elsewhere"))
        monkeypatch.chdir(deep)

        assert project_root() == project, "the boundary must not hide a real project"

    def test_an_explicit_start_is_still_honoured(self, home):
        project = home / "work" / "agent"
        (project / ".co").mkdir(parents=True)
        deep = project / "src"
        deep.mkdir()

        assert project_root(deep) == project
