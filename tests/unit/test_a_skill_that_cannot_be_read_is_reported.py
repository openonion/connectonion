"""A SKILL.md that cannot be read is reported by `co doctor`.

`_parse_skill_content` swallows a YAML error:

    try:
        frontmatter = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        frontmatter = {}

so a skill whose frontmatter has a typo — a tab, an unclosed bracket — loads
anyway, with no description and no `tools:` patterns. Measured on a live agent,
with a SKILL.md containing `this is not valid frontmatter\\n---\\nname: [unclosed`
and a second one of zero bytes:

    skill count      117 -> 119        both accepted
    startup          no warning
    listed as        name='broken' desc='No description'
                     name='empty'  desc='No description'
    co doctor        said nothing about either

Not a permissions hole — `frontmatter.get('tools', [])` grants the empty list,
so every tool call still asks. What the author gets is a skill that appears to
work: it is offered to the model with no idea what it is for, and an empty
SKILL.md replaces the user's message with nothing at all.

The fix is the one this file already chose for symlinks, and the one #422 chose
for policy files: keep loading forgiving, and tell the operator. `find_skill_problems`
exists for exactly this — "a link is a claim that a skill lives somewhere, and
that claim can be false". A SKILL.md is the same claim, and it can be false the
same way.

Only unambiguous breakage is reported. A SKILL.md with no frontmatter at all is
a legitimate way to write a simple skill — the whole file is the instructions —
and flagging it would report working skills as broken.
"""

import re

import pytest

from connectonion.useful_plugins.skills import find_skill_problems, _parse_skill_content


@pytest.fixture
def skills_dir(tmp_path):
    d = tmp_path / ".co" / "skills"
    d.mkdir(parents=True)
    return d


def _skill(skills_dir, name, content):
    (skills_dir / name).mkdir()
    (skills_dir / name / "SKILL.md").write_text(content)


def _problems_for(tmp_path, name):
    return [(loc, n, reason) for loc, n, reason
            in find_skill_problems(co_dir=tmp_path / ".co") if n == name]


BROKEN_YAML = "---\nname: [unclosed\ndescription: x\n---\n\nDo the thing.\n"
GOOD = "---\nname: fine\ndescription: a working skill\n---\n\nDo the thing.\n"


class TestFrontmatterThatDoesNotParse:

    def test_it_is_reported(self, tmp_path, skills_dir):
        _skill(skills_dir, "broken", BROKEN_YAML)

        assert _problems_for(tmp_path, "broken"), "a skill nobody can read was not reported"

    def test_the_reason_says_it_is_the_frontmatter(self, tmp_path, skills_dir):
        _skill(skills_dir, "broken", BROKEN_YAML)

        reason = _problems_for(tmp_path, "broken")[0][2]
        assert "frontmatter" in reason.lower(), reason

    def test_a_tab_in_the_yaml_is_caught_too(self, tmp_path, skills_dir):
        """The typo people actually make."""
        _skill(skills_dir, "tabbed", "---\nname: x\n\tdescription: y\n---\n\nGo.\n")

        assert _problems_for(tmp_path, "tabbed")


class TestTheTyposPeopleActuallyMake:
    """Both shapes are taken from real skills on this machine, not invented.

    Running the new check over the 117 skills installed here reported 7, and
    every one was genuine — the descriptions their authors wrote were never
    reaching the model:

        argument-hint: [analyze <person/org>] | [dig messages]
            unquoted `[` opens a flow sequence, then `|` reads as a block scalar

        description: …写到 frontmatter outline: 字段，结构层据此执行
            an unquoted colon inside a plain scalar

    Neither looks wrong to a human reading the file, which is why swallowing
    the error is the wrong thing to do with it.
    """

    def test_an_unquoted_bracket_and_pipe(self, tmp_path, skills_dir):
        _skill(skills_dir, "hinted",
               "---\nname: hinted\nargument-hint: [analyze <person>] | [dig messages]\n---\n\nGo.\n")

        assert _problems_for(tmp_path, "hinted")

    def test_an_unquoted_colon_inside_a_description(self, tmp_path, skills_dir):
        _skill(skills_dir, "colonic",
               "---\nname: colonic\ndescription: writes to frontmatter outline: field, then runs\n---\n\nGo.\n")

        assert _problems_for(tmp_path, "colonic")


class TestTheReasonPointsAtTheLine:
    """#422 settled this for policy files: a YAML error names where it is."""

    def test_a_line_number_is_given(self, tmp_path, skills_dir):
        _skill(skills_dir, "colonic",
               "---\nname: colonic\ndescription: writes to frontmatter outline: field\n---\n\nGo.\n")

        assert re.search(r'line \d+', _problems_for(tmp_path, "colonic")[0][2])

    def test_the_line_number_is_the_offending_line(self, tmp_path, skills_dir):
        """Counted in the SKILL.md, not inside the frontmatter — the number has
        to be the one the author's editor shows."""
        content = "---\nname: colonic\ndescription: writes to frontmatter outline: field\n---\n\nGo.\n"
        _skill(skills_dir, "colonic", content)

        reported = int(re.search(r'line (\d+)', _problems_for(tmp_path, "colonic")[0][2]).group(1))

        assert content.split('\n')[reported - 1].startswith('description:')


class TestAnEmptySkill:

    def test_a_zero_byte_skill_md_is_reported(self, tmp_path, skills_dir):
        _skill(skills_dir, "empty", "")

        assert _problems_for(tmp_path, "empty"), "an empty SKILL.md was not reported"

    def test_whitespace_only_counts_as_empty(self, tmp_path, skills_dir):
        _skill(skills_dir, "blank", "\n\n   \n")

        assert _problems_for(tmp_path, "blank")

    def test_the_reason_says_empty(self, tmp_path, skills_dir):
        _skill(skills_dir, "empty", "")

        assert "empty" in _problems_for(tmp_path, "empty")[0][2].lower()


class TestWhatMustNotBeReported:
    """Reporting a working skill as broken is worse than the bug."""

    def test_a_good_skill_is_silent(self, tmp_path, skills_dir):
        _skill(skills_dir, "fine", GOOD)

        assert not _problems_for(tmp_path, "fine")

    def test_a_skill_with_no_frontmatter_is_legitimate(self, tmp_path, skills_dir):
        """The whole file is the instructions. That is a supported way to write one."""
        _skill(skills_dir, "plain", "Just do the thing, carefully.\n")

        assert not _problems_for(tmp_path, "plain")

    def test_a_directory_that_is_not_a_skill_is_still_ignored(self, tmp_path, skills_dir):
        """People keep notes and shared assets in here — the docstring says so."""
        (skills_dir / "notes").mkdir()
        (skills_dir / "notes" / "todo.md").write_text("later")

        assert not _problems_for(tmp_path, "notes")

    def test_a_dotfile_directory_is_still_ignored(self, tmp_path, skills_dir):
        (skills_dir / ".git").mkdir()
        (skills_dir / ".git" / "SKILL.md").write_text("")

        assert not _problems_for(tmp_path, ".git")


class TestLoadingStaysForgiving:
    """Reported, not raised — a broken skill must not stop the agent starting."""

    def test_parsing_broken_frontmatter_still_returns(self):
        """Returns rather than raises — which is what this class is about.

        It also asserted `frontmatter == {}`. The name and description are now
        rescued from a file YAML rejects, because returning nothing made the
        skill invisible to the model instead of merely unconfigured. Nothing
        with consequences is rescued; see test_a_colon_does_not_hide_a_skill.
        """
        frontmatter, instructions = _parse_skill_content(BROKEN_YAML)

        assert frontmatter["description"] == "x"
        assert "Do the thing." in instructions

    def test_parsing_an_empty_file_still_returns(self):
        assert _parse_skill_content("") == ({}, "")
