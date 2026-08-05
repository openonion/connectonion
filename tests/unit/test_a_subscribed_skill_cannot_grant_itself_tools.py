"""A skill fetched from the relay arrives with permission grants attached.

`sub_commands.py` states the trust assumption in its own header:

    v1 trusts the relay — no Ed25519 signature verification (relay strips
    signer/signature from profile responses).

An honest limitation. What makes it worth acting on before a long-term release
is that a `SKILL.md` is not only instructions. Its frontmatter carries a
`tools:` list, and invoking the skill auto-approves those patterns for the
turn. Measured on a real agent earlier in this release:

    during the turn : ['Bash(git status)', 'read_file']

So a synced skill does not merely suggest what an agent should do — it arrives
asking for auto-approval, from a source nobody verified. And it is written
verbatim, then fanned out by `install_all()` into `~/.claude`, `~/.codex`,
`~/.openclaw`, `~/.cursor` and `~/.kiro`: one `co sub sync` puts unverified
content into five agents' skill directories, four of which are not ours.

This is #654's option 2, plus option 1. A subscribed skill keeps its
instructions and loses its ability to pre-authorise anything; the operator adds
patterns themselves if they want them, in their own `.co/host.yaml`, where the
decision is theirs and visible.

BEHAVIOUR CHANGE: a subscribed skill that used to auto-approve `Bash(git
status)` now asks. That is the point, but it is a change.

Option 3 — verifying the publisher's signature — is the real answer and needs
the relay to stop stripping it. Not doable from this repository.
"""

import pytest

from connectonion.cli.commands.sub_commands import strip_tool_grants


WITH_TOOLS = """---
name: deploy-helper
description: Ships the thing
tools:
  - Bash(git status)
  - read_file
---

Run the deploy and report what happened.
"""

WITHOUT_TOOLS = """---
name: plain
description: Just instructions
---

Do the thing.
"""

NO_FRONTMATTER = "The whole file is the instructions.\n"


class TestTheGrantIsRemoved:

    def test_the_tools_list_is_gone(self):
        out = strip_tool_grants(WITH_TOOLS, "deploy-helper")

        assert "Bash(git status)" not in out
        assert "read_file" not in out

    def test_the_instructions_survive(self):
        out = strip_tool_grants(WITH_TOOLS, "deploy-helper")

        assert "Run the deploy and report what happened." in out

    def test_the_rest_of_the_frontmatter_survives(self):
        out = strip_tool_grants(WITH_TOOLS, "deploy-helper")

        assert "name: deploy-helper" in out
        assert "description: Ships the thing" in out

    def test_it_still_parses_as_a_skill(self):
        import yaml

        out = strip_tool_grants(WITH_TOOLS, "deploy-helper")
        front = out.split("---")[1]

        assert yaml.safe_load(front)["name"] == "deploy-helper"

    def test_it_says_what_it_removed(self):
        """Silence would leave the operator wondering why the skill behaves
        differently from the publisher's copy."""
        out = strip_tool_grants(WITH_TOOLS, "deploy-helper")

        assert "tools" in out.lower()
        assert "removed" in out.lower() or "not granted" in out.lower()


class TestSkillsWithNothingToStrip:

    def test_one_without_tools_is_untouched(self):
        assert strip_tool_grants(WITHOUT_TOOLS, "plain") == WITHOUT_TOOLS

    def test_one_without_frontmatter_is_untouched(self):
        """A file with no frontmatter is a legitimate simple skill — the whole
        file is the prompt (#629)."""
        assert strip_tool_grants(NO_FRONTMATTER, "simple") == NO_FRONTMATTER

    def test_an_empty_body_is_untouched(self):
        assert strip_tool_grants("", "empty") == ""

    def test_unparseable_frontmatter_is_left_alone(self):
        """Not ours to repair, and rewriting what we cannot read is worse than
        passing it through — the skill loader reports it (#629)."""
        broken = "---\nname: [unclosed\n---\n\nbody\n"

        assert strip_tool_grants(broken, "broken") == broken


class TestTheOperatorIsToldBeforeItLands:
    """#654's option 1: the warning was at lines 23-24 of a module docstring,
    and `co sub sync --help` said nothing. The person taking the risk is the
    one who did not see it."""

    def test_the_help_text_mentions_it(self):
        import inspect

        from connectonion.cli import main

        source = inspect.getsource(main)
        sync_help = source[source.index("def sub_sync"):][:1200] if "def sub_sync" in source else source

        assert "unverified" in sync_help.lower() or "not verified" in sync_help.lower(), (
            "co sub sync --help still does not say the content is unverified"
        )
