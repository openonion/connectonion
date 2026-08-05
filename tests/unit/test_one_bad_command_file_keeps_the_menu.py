"""One typo in one command file and there are no commands at all.

`list_all()` is the menu — `slash_command.py` says so — and it parses every
`.md` in both command directories through `_parse_file`, which raises:

    if not content.startswith("---"):
        raise ValueError(f"Command file {filepath} missing YAML frontmatter")

So a single bad file loses every good one:

    .co/commands/good.md      valid frontmatter
    .co/commands/broken.md    no frontmatter

    list_all()     -> ValueError: Command file .../broken.md missing YAML frontmatter
    load('good')   -> works

The good command is individually loadable. It is only the listing that dies,
which means the user sees no commands and a traceback, for a typo in a file
they may not even have opened.

#629 settled the same question for skills and is the shape copied here: a
`_why_the_..._cannot_be_read` predicate that **checks** rather than catches, so
the listing names the broken file and keeps the rest.

What this deliberately does not decide is whether a command with no frontmatter
should work the way a skill with no frontmatter does — where the whole file is
the prompt and the name comes from the filename. The two subsystems disagree
about identical input today. That is a format decision; `list_all()` losing
everything is a bug either way, and it is the only thing fixed here.
"""

import pytest

from connectonion.useful_tools.slash_command import SlashCommand


GOOD = """---
name: deploy
description: Ship it
---

Do the deploy.
"""

NO_FRONTMATTER = "Just some notes I left in this folder.\n"
UNCLOSED = "---\nname: half\n"
BAD_YAML = "---\nname: [unclosed\ndescription: x\n---\n\nbody\n"
NO_NAME = "---\ndescription: nameless\n---\n\nbody\n"
EMPTY = ""


@pytest.fixture
def commands(tmp_path, monkeypatch):
    """A project whose .co/commands/ is `files`."""
    def write(**files):
        co = tmp_path / ".co" / "commands"
        co.mkdir(parents=True, exist_ok=True)
        for stem, text in files.items():
            (co / f"{stem}.md").write_text(text, encoding="utf-8")
        monkeypatch.setattr("connectonion.useful_tools.slash_command.project_co_dir",
                            lambda: tmp_path / ".co")
        monkeypatch.setattr("connectonion.useful_tools.slash_command.project_root",
                            lambda: tmp_path / "no-builtins-here")
        return co
    return write


class TestTheMenuSurvivesOneBadFile:

    @pytest.mark.parametrize("bad", [NO_FRONTMATTER, UNCLOSED, BAD_YAML, NO_NAME, EMPTY])
    def test_the_good_command_is_still_listed(self, commands, bad):
        commands(good=GOOD, broken=bad)

        assert "deploy" in SlashCommand.list_all()

    def test_the_broken_one_is_not_invented(self, commands):
        commands(good=GOOD, broken=NO_FRONTMATTER)

        assert list(SlashCommand.list_all()) == ["deploy"]

    def test_several_bad_files_do_not_add_up(self, commands):
        commands(good=GOOD, a=NO_FRONTMATTER, b=BAD_YAML, c=EMPTY)

        assert list(SlashCommand.list_all()) == ["deploy"]

    def test_all_bad_is_an_empty_menu_not_a_traceback(self, commands):
        commands(a=NO_FRONTMATTER, b=BAD_YAML)

        assert SlashCommand.list_all() == {}


class TestTheOperatorIsToldWhichFile:
    """Silence would be its own bug — #629's whole point was that a dropped
    entry is indistinguishable from one that was never there."""

    def test_the_problem_names_the_file(self, commands):
        co = commands(good=GOOD, broken=NO_FRONTMATTER)
        _, problems = SlashCommand.list_all(report=True)

        assert any("broken.md" in str(p) for p in problems), problems

    def test_it_says_what_is_wrong(self, commands):
        commands(good=GOOD, broken=NO_NAME)
        _, problems = SlashCommand.list_all(report=True)

        assert any("name" in str(p).lower() for p in problems), problems

    def test_a_clean_directory_reports_nothing(self, commands):
        commands(good=GOOD)
        listed, problems = SlashCommand.list_all(report=True)

        assert list(listed) == ["deploy"]
        assert problems == []


class TestLoadingOneByNameIsUnchanged:
    """`load()` still raises — a command you asked for by name and cannot have
    is an error, not something to skip past silently."""

    def test_a_good_one_loads(self, commands):
        commands(good=GOOD)

        assert SlashCommand.load("good").name == "deploy"

    def test_a_broken_one_still_raises(self, commands):
        commands(broken=NO_FRONTMATTER)

        with pytest.raises(ValueError):
            SlashCommand.load("broken")
