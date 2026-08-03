"""A new project carries a .gitignore before it carries a git repo.

`setup_gitignore()` returns early unless the directory — or the current one —
is already a git repo:

    git_dir = project_dir / ".git"
    parent_git = Path.cwd() / ".git"
    if not git_dir.exists() and not parent_git.exists():
        return None

So the ordinary way to start a project produces no .gitignore at all:

    co create my-agent          # .env: OPENONION_API_KEY, CO_INVITE_CODE
    cd my-agent
    git init && git add . && git commit && git push

`git init` after `co create` is the normal order — the project is made first
and versioned once it works. By then the file that would have excluded `.env`
was never written, and `git add .` takes the agent's API token and the code
that lets a stranger onboard.

An unused .gitignore in a directory that never becomes a repo costs a few
bytes. A missing one costs a published token, and the recovery is to rotate
every key in it.

This was already known — the comment in env_inheritance.py describes the same
window: "with a .gitignore written only when the directory was already a git
repo — one `git add .` from being published".
"""

from pathlib import Path

import pytest

from connectonion.cli.commands.project_cmd_lib import setup_gitignore


class TestItIsWrittenBeforeThereIsARepo:

    def test_a_plain_directory_gets_one(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        project = tmp_path / "my-agent"
        project.mkdir()

        setup_gitignore(project)

        assert (project / ".gitignore").exists()

    def test_it_excludes_the_env_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        project = tmp_path / "my-agent"
        project.mkdir()

        setup_gitignore(project)

        assert ".env" in (project / ".gitignore").read_text()


class TestNothingElseChanges:

    def test_an_existing_gitignore_is_appended_to_not_replaced(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        project = tmp_path / "my-agent"
        project.mkdir()
        (project / ".gitignore").write_text("node_modules/\n")

        setup_gitignore(project)

        text = (project / ".gitignore").read_text()
        assert "node_modules/" in text
        assert ".env" in text

    def test_it_is_not_added_twice(self, tmp_path, monkeypatch):
        """Running create twice, or create then init, must not stack copies."""
        monkeypatch.chdir(tmp_path)
        project = tmp_path / "my-agent"
        project.mkdir()

        setup_gitignore(project)
        setup_gitignore(project)

        text = (project / ".gitignore").read_text()
        assert text.count("# ConnectOnion") == 1, text

    def test_a_real_repo_still_works(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        project = tmp_path / "my-agent"
        (project / ".git").mkdir(parents=True)

        setup_gitignore(project)

        assert ".env" in (project / ".gitignore").read_text()
