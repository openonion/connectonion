"""`co doctor` reports skills that now work, and does not say what is lost.

After the loader learned to rescue `name` and `description` from a frontmatter
YAML rejects, eight skills on this machine went from invisible-to-the-model to
working. `co doctor` still says:

    ✗ Diagnostics complete — 8 problems
      • skill user/outline-plan: SKILL.md frontmatter is not valid YAML at line 3

which overstates it. The function deciding this is called
`_why_the_skill_cannot_be_read`, and its own docstring sets the bar:

    Only unambiguous breakage. ... reporting a working skill is worse than the
    silence this fixes.

The file is still malformed and something *is* still lost: `tools:` is not
rescued, on purpose, because it grants permissions. So the report should
separate the two cases it currently merges.

    a broken file that declares `tools:`      the declaration is silently
                                              ignored — a real problem
    a broken file that declares no tools      name and description came through
                                              — worth fixing, nothing is broken

A user reading "8 problems" on a machine where all eight skills work learns to
ignore the doctor, which costs more than the wrong quoting did.
"""

import pytest

from connectonion.useful_plugins.skills import _why_the_skill_cannot_be_read


BROKEN_NO_TOOLS = """---
name: outline-plan
description: Rework the outline: start from the reader's pain.
---

# Outline
"""

BROKEN_WITH_TOOLS = """---
name: deployer
description: Ship it: carefully.
tools: bash
---

# Deployer
"""

UNREADABLE = """---
name: [unclosed
---

# Nope
"""

FINE = """---
name: commit
description: Create git commits
tools:
  - read_file
---

# Commit
"""


def _write(tmp_path, content):
    skill = tmp_path / "SKILL.md"
    skill.write_text(content, encoding="utf-8")
    return skill


class TestABrokenFileThatDeclaresToolsIsAProblem:
    """The declaration does nothing, and the author cannot tell."""

    def test_it_is_reported(self, tmp_path):
        assert _why_the_skill_cannot_be_read(_write(tmp_path, BROKEN_WITH_TOOLS))

    def test_it_says_the_tools_are_ignored(self, tmp_path):
        reason = _why_the_skill_cannot_be_read(_write(tmp_path, BROKEN_WITH_TOOLS))

        assert "tools" in reason

    def test_it_still_gives_the_line(self, tmp_path):
        reason = _why_the_skill_cannot_be_read(_write(tmp_path, BROKEN_WITH_TOOLS))

        assert "line 3" in reason


class TestABrokenFileWithoutToolsSaysWhatSurvived:
    """It works. Saying "cannot be read" of a working skill teaches people to
    stop reading the doctor."""

    def test_it_is_still_mentioned(self, tmp_path):
        """Silence would leave the malformed file to rot."""
        assert _why_the_skill_cannot_be_read(_write(tmp_path, BROKEN_NO_TOOLS))

    def test_it_does_not_claim_the_skill_is_unusable(self, tmp_path):
        reason = _why_the_skill_cannot_be_read(_write(tmp_path, BROKEN_NO_TOOLS))

        assert "cannot" not in reason.lower()

    def test_it_says_the_description_came_through(self, tmp_path):
        reason = _why_the_skill_cannot_be_read(_write(tmp_path, BROKEN_NO_TOOLS))

        assert "description" in reason

    def test_the_loader_agrees_the_skill_works(self, tmp_path):
        """The claim in the message has to match what loading really does."""
        from connectonion.useful_plugins.skills import _parse_skill_content

        frontmatter, _ = _parse_skill_content(BROKEN_NO_TOOLS)

        assert frontmatter["description"].startswith("Rework the outline")


class TestAllowedToolsIsNotOurKey:
    """`allowed-tools:` belongs to another tool and _tool_patterns never reads it.

    The first version of this message counted it, so a file declaring only
    `allowed-tools` was told its tools were being ignored *because of* the bad
    quoting. They are ignored either way — most of the real files on this machine
    declare exactly that, so the wrong claim would have been the common case.
    """

    ALLOWED_TOOLS_ONLY = """---
allowed-tools: Read, Edit, Glob
description: Rework the outline: from the pain.
---

# Outline
"""

    def test_it_says_the_permission_declaration_is_ignored(self, tmp_path):
        reason = _why_the_skill_cannot_be_read(
            _write(tmp_path, self.ALLOWED_TOOLS_ONLY)
        )

        assert "allowed-tools" in reason
        assert "ignored" in reason

    def test_it_says_what_did_survive(self, tmp_path):
        reason = _why_the_skill_cannot_be_read(
            _write(tmp_path, self.ALLOWED_TOOLS_ONLY)
        )

        assert "description" in reason

    def test_the_loader_never_grants_from_allowed_tools(self, tmp_path):
        """Even in a well-formed file, so the message is right to ignore it."""
        from connectonion.useful_plugins.skills import _tool_patterns

        assert _tool_patterns({"allowed-tools": "Read, Edit"}) == []

    def test_valid_yaml_is_still_reported_by_doctor(self, tmp_path):
        skill = _write(tmp_path, """---
name: claude-helper
description: A valid Claude Code skill
allowed-tools: Bash(git status) Read
---

# Helper
""")

        reason = _why_the_skill_cannot_be_read(skill)

        assert "allowed-tools" in reason
        assert "not auto-approve" in reason

    def test_invoking_the_skill_warns_once(self, tmp_path, monkeypatch):
        import importlib

        skills = importlib.import_module("connectonion.useful_plugins.skills")

        skill_dir = tmp_path / "claude-helper"
        skill_dir.mkdir()
        skill = skill_dir / "SKILL.md"
        skill.write_text("""---
name: claude-helper
description: A valid Claude Code skill
allowed-tools: Bash(git status) Read
---

# Helper
""", encoding="utf-8")
        monkeypatch.setattr(skills, "_get_skill_paths", lambda _: [skill])
        skills._WARNED_ALLOWED_TOOLS.clear()

        with pytest.warns(UserWarning, match="allowed-tools.*not auto-approved") as seen:
            skills._load_skill("claude-helper")
            skills._load_skill("claude-helper")

        assert len(seen) == 1


class TestTheGenuinelyUnreadableStaysUnreadable:

    def test_a_file_whose_name_cannot_be_read_is_reported(self, tmp_path):
        assert _why_the_skill_cannot_be_read(_write(tmp_path, UNREADABLE))

    def test_an_empty_file_is_reported(self, tmp_path):
        assert _why_the_skill_cannot_be_read(_write(tmp_path, "")) == "SKILL.md is empty"

    def test_a_good_file_is_not_reported(self, tmp_path):
        assert _why_the_skill_cannot_be_read(_write(tmp_path, FINE)) is None

    def test_no_frontmatter_at_all_is_not_reported(self, tmp_path):
        """A whole-file skill is a legitimate way to write one."""
        assert _why_the_skill_cannot_be_read(_write(tmp_path, "# Just prose\n")) is None
