"""Which directory `co skills copy` writes to, and why it decides everything.

`~/.co/skills` is the operator's library and does not travel — `co skills list`
marks it `Deploys ✗`. Only a project's `.co/skills` reaches a server. Every
deploy printed "move one into .co/skills/ to ship it" and no command did that,
so the operator was left to `cp -R` by hand. openonion/connectonion#408
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectonion.cli.commands import skills_commands as sc


@pytest.fixture
def discovered(tmp_path, monkeypatch):
    """One skill in the index, living outside any project."""
    library = tmp_path / "library" / "greeter"
    library.mkdir(parents=True)
    (library / "SKILL.md").write_text("---\nname: greeter\n---\n\nhello\n")
    (library / "helper.py").write_text("print('shipped too')\n")

    index = {"skills": [{"name": "greeter", "source": "claude",
                         "path": str(library / "SKILL.md")}]}
    monkeypatch.setattr(sc, "_load_index", lambda: index)
    monkeypatch.setattr(sc, "SKILLS_DIR", tmp_path / "user-tier" / "skills")
    monkeypatch.chdir(tmp_path / "project")
    return tmp_path


@pytest.fixture(autouse=True)
def project_dir(tmp_path):
    (tmp_path / "project").mkdir(parents=True, exist_ok=True)


class TestCopyingIntoTheProject:
    def test_to_project_lands_in_the_tier_that_deploys(self, discovered):
        sc.handle_skills_copy(["greeter"], to_project=True)

        assert (Path.cwd() / ".co" / "skills" / "greeter" / "SKILL.md").exists()

    def test_the_skills_own_files_come_with_it(self, discovered):
        """A skill is a directory, not a single markdown file."""
        sc.handle_skills_copy(["greeter"], to_project=True)

        assert (Path.cwd() / ".co" / "skills" / "greeter" / "helper.py").exists()

    def test_without_the_flag_it_still_goes_to_the_user_library(self, discovered):
        sc.handle_skills_copy(["greeter"])

        assert (sc.SKILLS_DIR / "greeter" / "SKILL.md").exists()
        assert not (Path.cwd() / ".co" / "skills" / "greeter").exists()

    def test_all_respects_the_destination_too(self, discovered):
        sc.handle_skills_copy([], all_=True, to_project=True)

        assert (Path.cwd() / ".co" / "skills" / "greeter" / "SKILL.md").exists()
