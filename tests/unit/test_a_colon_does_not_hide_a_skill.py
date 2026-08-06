"""A colon in a description makes the skill invisible to the model.

`_parse_skill_content` parses frontmatter with strict YAML and, on failure,
carries on with nothing:

    try:
        frontmatter = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError:
        frontmatter = {}

The description is how the model decides whether a skill applies — it is
rendered into the prompt as

    - `/oo` (user): {description}

so an empty frontmatter means the model is told the skill exists and nothing
about when to use it. It is never chosen, and nothing says why. `skills.py`
already describes this exact outcome, in the comment explaining why
`co doctor` reports these files:

    loading swallows a YAML error and carries on with an empty frontmatter, so
    the skill reaches the model with no description and no `tools:` patterns,
    looking like it works

The detection was built. The swallowing was left.

## It is not a rare shape

An unquoted colon inside a value is invalid YAML and is what people write.
Measured on this machine's own skills, all authored by Claude Code:

    outline-plan   description: …写到 frontmatter outline: 字段…
    linkedin-…     description: …from a local Markdown draft: prepare or generate…
    oo             argument-hint: [0xAddress <task>] | [init|publish|…]

Eight of the installed skills, and Claude Code loads every one of them. The
CLI's own `parse_frontmatter` in skills_commands.py reads them too — it scans
`key: value` lines rather than parsing YAML. So two parsers in this repo
disagree about the same file, and the one the *agent* uses at runtime is the
one that gives up.

The fix keeps strict YAML first and falls back to that line scan, so a
recoverable file still reaches the model with its description. `co doctor` goes
on reporting the file, because a `tools:` list is not recoverable that way and
the file should still be fixed — but a badly quoted description no longer
silently removes a skill.
"""

import pytest

from connectonion.useful_plugins.skills import _parse_skill_content


COLON_IN_DESCRIPTION = """---
name: linkedin-article-orchestrator
description: Orchestrate a full LinkedIn article workflow from a local Markdown draft: prepare or generate a cover, draft and verify the article.
---

# LinkedIn Article Orchestrator

Do the thing.
"""

PIPE_IN_ARGUMENT_HINT = """---
name: oo
description: Entry point for anything `oo` related. Routes to the right sub-skill.
argument-hint: [0xAddress <task>] | [init|publish|subscribe|accept]
---

# oo
"""

VALID = """---
name: commit
description: Create git commits
tools:
  - read_file
  - write_file
---

# Commit
Body here.
"""


class TestARecoverableFileKeepsItsDescription:

    def test_a_colon_in_the_description_survives(self):
        frontmatter, _ = _parse_skill_content(COLON_IN_DESCRIPTION)

        assert frontmatter.get("description", "").startswith(
            "Orchestrate a full LinkedIn article workflow"
        )

    def test_the_name_survives_too(self):
        frontmatter, _ = _parse_skill_content(COLON_IN_DESCRIPTION)

        assert frontmatter["name"] == "linkedin-article-orchestrator"

    def test_the_whole_description_is_kept_not_the_part_before_the_colon(self):
        frontmatter, _ = _parse_skill_content(COLON_IN_DESCRIPTION)

        assert "prepare or generate a cover" in frontmatter["description"]

    def test_a_pipe_in_another_field_does_not_lose_the_description(self):
        frontmatter, _ = _parse_skill_content(PIPE_IN_ARGUMENT_HINT)

        assert "Entry point for anything" in frontmatter["description"]

    def test_the_instructions_still_come_back(self):
        _, instructions = _parse_skill_content(COLON_IN_DESCRIPTION)

        assert instructions.startswith("# LinkedIn Article Orchestrator")


class TestABrokenFileGrantsNothing:
    """The property the strict reader was chosen for, kept.

    test_one_reader_for_skill_frontmatter recorded it as "neither invents a
    reading of a file that has a syntax error in it". `tools:` is fed to
    _grant_skill_permissions, so guessing it from a line split would widen an
    agent's permissions on the strength of a file that does not parse. Only
    `name` and `description` are rescued, and neither grants anything.
    """

    BROKEN_WITH_TOOLS = """---
name: sneaky
description: A description with a colon: right here.
tools: bash
---

# Sneaky
"""

    def test_tools_is_not_recovered(self):
        frontmatter, _ = _parse_skill_content(self.BROKEN_WITH_TOOLS)

        assert "tools" not in frontmatter

    def test_no_permission_pattern_comes_out_of_it(self):
        from connectonion.useful_plugins.skills import _tool_patterns

        frontmatter, _ = _parse_skill_content(self.BROKEN_WITH_TOOLS)

        assert _tool_patterns(frontmatter) == []

    def test_the_description_is_still_rescued(self):
        frontmatter, _ = _parse_skill_content(self.BROKEN_WITH_TOOLS)

        assert frontmatter["description"].startswith("A description with a colon")

    def test_nothing_else_is_rescued_either(self):
        frontmatter, _ = _parse_skill_content(self.BROKEN_WITH_TOOLS)

        assert set(frontmatter) <= {"name", "description"}

    def test_a_valid_file_still_grants_its_tools(self):
        from connectonion.useful_plugins.skills import _tool_patterns

        frontmatter, _ = _parse_skill_content(VALID)

        assert _tool_patterns(frontmatter) == ["read_file", "write_file"]


class TestValidYamlIsUnaffected:
    """The fallback must not take over parsing from YAML."""

    def test_a_valid_file_still_parses(self):
        frontmatter, _ = _parse_skill_content(VALID)

        assert frontmatter["name"] == "commit"

    def test_a_yaml_list_is_still_a_list(self):
        frontmatter, _ = _parse_skill_content(VALID)

        assert frontmatter["tools"] == ["read_file", "write_file"]

    def test_the_body_is_unchanged(self):
        _, instructions = _parse_skill_content(VALID)

        assert instructions == "# Commit\nBody here."

    def test_a_file_with_no_frontmatter_is_all_instructions(self):
        frontmatter, instructions = _parse_skill_content("# Just a skill\n\nDo it.")

        assert frontmatter == {}
        assert instructions == "# Just a skill\n\nDo it."


class TestTheTwoParsersAgree:
    """The CLI reads these files; the runtime must not disagree about them."""

    @pytest.mark.parametrize(
        "content", [COLON_IN_DESCRIPTION, PIPE_IN_ARGUMENT_HINT, VALID]
    )
    def test_the_description_matches_the_cli(self, content):
        from connectonion.cli.commands.skills_commands import parse_frontmatter

        runtime, _ = _parse_skill_content(content)

        assert runtime.get("description") == parse_frontmatter(content).get(
            "description"
        )


class TestWhatCannotBeRecoveredIsStillReported:
    """doctor must keep flagging the file: a `tools:` list is still lost."""

    def test_doctor_still_calls_it_unreadable(self, tmp_path):
        from connectonion.useful_plugins.skills import _why_the_skill_cannot_be_read

        skill = tmp_path / "SKILL.md"
        skill.write_text(COLON_IN_DESCRIPTION, encoding="utf-8")

        assert _why_the_skill_cannot_be_read(skill) is not None

    def test_a_valid_file_is_not_flagged(self, tmp_path):
        from connectonion.useful_plugins.skills import _why_the_skill_cannot_be_read

        skill = tmp_path / "SKILL.md"
        skill.write_text(VALID, encoding="utf-8")

        assert _why_the_skill_cannot_be_read(skill) is None
