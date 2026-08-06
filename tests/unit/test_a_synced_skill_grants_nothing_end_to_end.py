"""A subscribed skill grants nothing — checked through both halves at once.

Two modules have to agree for this to hold, and each is tested alone:

    sub_commands.strip_tool_grants   removes `tools:` on sync — unless the
                                     frontmatter does not parse, because
                                     rewriting what we cannot read is worse
                                     (#654, #708)

    skills._read_frontmatter         recovers only name and description from a
                                     frontmatter YAML rejects, deliberately not
                                     `tools:`, which is fed to
                                     _grant_skill_permissions

So the unparseable case is covered by the *second* half: the file keeps its
`tools:` line and the loader never turns it into a grant. Neither file's tests
say that, and it is the kind of property a future "improvement" to the loader —
recovering one more key — would remove without anything going red.

Measured before writing this:

    valid YAML   + tools:  ->  stripped, note added, patterns []
    broken YAML  + tools:  ->  passed through with `tools: bash` intact,
                               loader keys ['description', 'name'], patterns []

The relay strips the publisher's signature (v1 trusts it), so the content this
runs on is unverified by design; that is #654 option 3 and needs the relay.
"""

import pytest

from connectonion.cli.commands.sub_commands import strip_tool_grants
from connectonion.useful_plugins.skills import _parse_skill_content, _tool_patterns


def _granted(body):
    """What an agent would auto-approve after this skill is synced and loaded."""
    frontmatter, _ = _parse_skill_content(strip_tool_grants(body, "synced"))
    return _tool_patterns(frontmatter)


VALID = """---
name: helper
description: Do a thing
tools: bash
---

# Helper
Run it.
"""

BROKEN = """---
name: sneaky
description: Do the thing: carefully.
tools: bash
---

# Sneaky
Run it.
"""

BROKEN_LIST = """---
name: sneakier
description: Colons: everywhere: here
tools:
  - bash
  - write
---

# Sneakier
"""

NO_FRONTMATTER = "# Just prose\n\nDo the thing.\n"


class TestNothingIsGrantedByASyncedSkill:

    @pytest.mark.parametrize(
        "label,body",
        [("valid yaml", VALID), ("broken yaml", BROKEN),
         ("broken yaml, list form", BROKEN_LIST),
         ("no frontmatter", NO_FRONTMATTER)],
    )
    def test_it_auto_approves_nothing(self, label, body):
        assert _granted(body) == [], (
            f"a synced skill with {label} still arrives with a permission grant"
        )


class TestEachHalfDoesItsOwnPart:
    """Named so a failure says which half moved."""

    def test_the_strip_removes_a_parseable_grant(self):
        assert "tools" not in strip_tool_grants(VALID, "synced").split("---")[1]

    def test_the_strip_leaves_an_unparseable_file_alone(self):
        """Not a gap — the loader is what stops this one."""
        assert "tools: bash" in strip_tool_grants(BROKEN, "synced")

    def test_the_loader_refuses_to_recover_tools(self):
        frontmatter, _ = _parse_skill_content(BROKEN)

        assert "tools" not in frontmatter
        assert set(frontmatter) <= {"name", "description"}

    def test_the_loader_still_recovers_what_is_harmless(self):
        """Because the alternative was a skill invisible to the model."""
        frontmatter, _ = _parse_skill_content(BROKEN)

        assert frontmatter["description"].startswith("Do the thing")


class TestALocalSkillIsUnaffected:
    """Only *subscribed* skills lose their grant; your own keep it."""

    def test_a_valid_local_skill_still_grants(self):
        frontmatter, _ = _parse_skill_content(VALID)

        assert _tool_patterns(frontmatter) == ["bash"]

    def test_a_local_list_grant_survives(self):
        body = "---\nname: n\ndescription: d\ntools:\n  - bash\n  - write\n---\n\n# B\n"
        frontmatter, _ = _parse_skill_content(body)

        assert _tool_patterns(frontmatter) == ["bash", "write"]
