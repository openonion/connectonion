"""SKILL.md has one meaning, whichever part of the code reads it.

It had two readers. `useful_plugins/skills.py` parses YAML; `co_ai/skills/loader.py`
split each line on the first colon:

    for line in match.group(1).split('\\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            frontmatter[key.strip()] = value.strip()

They disagree in both directions, measured on real skills installed on this
machine:

    feishu-data-analysis   YAML: {}                 line-split: name, description, …
    outline-plan           YAML: {}                 line-split: allowed-tools, description, …
    tools: [read_file, write_file]
                           YAML: ['read_file', 'write_file']
                           line-split: '[read_file, write_file]'   (a string)

So the same skill behaved differently depending on whether the agent's skills
plugin or `co ai` loaded it, and neither said anything. The line splitter also
cannot represent what YAML can — block scalars and multi-line values arrive
truncated or as a stray key.

YAML is the documented format and the one the bundled skills are written in
(all 9 parse cleanly), so it is the reader that stays. #629 made `co doctor`
name the file and line of a frontmatter that does not parse, which is what
makes converging on the stricter reader safe to do: the skills that stop
being read silently are now the skills that get reported loudly.

Second half of the same issue: `tools:` is fed straight to
`_grant_skill_permissions`, which does `for pattern in patterns`. YAML returns
a *string* for `tools: read_file`, so the loop walked the characters and
registered `r`, `e`, `a`, `d`… as permission patterns. Fail-safe — no single
character matches a real tool — but the author's declaration did nothing.
"""

import pytest

from connectonion.cli.co_ai.skills.loader import parse_skill_frontmatter
from connectonion.useful_plugins.skills import _parse_skill_content


GOOD = """---
name: deploy
description: Ship the thing
tools: [read_file, write]
---

# Deploy

Do the deploy.
"""


class TestBothReadersAgree:

    @pytest.mark.parametrize("key", ["name", "description"])
    def test_on_the_keys_co_ai_uses(self, key):
        yaml_side, _ = _parse_skill_content(GOOD)

        assert parse_skill_frontmatter(GOOD)[key] == yaml_side[key]

    def test_on_a_list_being_a_list(self):
        """The line splitter handed back the string '[read_file, write]'."""
        assert parse_skill_frontmatter(GOOD)["tools"] == ["read_file", "write"]

    def test_on_a_frontmatter_that_does_not_parse(self):
        """One reader accepted what the other rejected. Now neither invents a
        reading of a file that has a syntax error in it."""
        broken = "---\nname: x\nargument-hint: [a] | [b]\n---\n\nBody.\n"

        yaml_side, _ = _parse_skill_content(broken)

        assert parse_skill_frontmatter(broken) == yaml_side == {}


class TestScalarToolsIsOnePattern:
    """`tools: read_file` is a pattern, not nine of them."""

    def test_a_scalar_becomes_a_one_element_list(self):
        from connectonion.useful_plugins.skills import _tool_patterns

        assert _tool_patterns({"tools": "read_file"}) == ["read_file"]

    def test_a_list_is_left_alone(self):
        from connectonion.useful_plugins.skills import _tool_patterns

        assert _tool_patterns({"tools": ["read_file", "write"]}) == ["read_file", "write"]

    def test_no_tools_key_is_empty(self):
        from connectonion.useful_plugins.skills import _tool_patterns

        assert _tool_patterns({}) == []

    def test_the_characters_are_not_patterns(self):
        """What the bug produced, named so it cannot come back quietly."""
        from connectonion.useful_plugins.skills import _tool_patterns

        assert "r" not in _tool_patterns({"tools": "read_file"})


class TestWhatCoAiStillDoesOnItsOwn:
    """Its fallbacks are its own and must survive the reader changing."""

    def test_the_name_falls_back_to_the_directory(self, tmp_path):
        from connectonion.cli.co_ai.skills.loader import _parse_skill_file

        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("---\ndescription: no name key\n---\n\nBody.\n")

        assert _parse_skill_file(d / "SKILL.md").name == "my-skill"

    def test_the_description_falls_back_to_the_first_paragraph(self, tmp_path):
        from connectonion.cli.co_ai.skills.loader import _parse_skill_file

        d = tmp_path / "s"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: s\n---\n\n# Title\n\nWhat it does.\n")

        assert "What it does." in _parse_skill_file(d / "SKILL.md").description

    def test_a_file_with_no_frontmatter_still_loads(self, tmp_path):
        from connectonion.cli.co_ai.skills.loader import _parse_skill_file

        d = tmp_path / "plain"
        d.mkdir()
        (d / "SKILL.md").write_text("Just the instructions.\n")

        info = _parse_skill_file(d / "SKILL.md")
        assert info.name == "plain"


class TestYamlTypesDoNotEscapeIntoTheName:
    """The reader changed; what the callers get must not.

    The line splitter always handed back strings. YAML types its values, so
    switching to it made `name: 123` an int and `name: no` a bool — YAML reads
    `no`, `on`, `yes` and `off` as booleans. The registry is built with
    `{s.name: s for s in skills}`, so a skill keyed by `False` cannot be looked
    up by any name a user can type, and it fails that way silently.

    Structured values like `tools: [a, b]` still arrive as a list — that is the
    reason to use YAML. It is the two human-facing labels that are pinned.
    """

    def _skill(self, tmp_path, folder, content):
        from connectonion.cli.co_ai.skills.loader import _parse_skill_file

        d = tmp_path / folder
        d.mkdir()
        (d / "SKILL.md").write_text(content)
        return _parse_skill_file(d / "SKILL.md")

    def test_a_numeric_name_is_a_string(self, tmp_path):
        info = self._skill(tmp_path, "numeric", "---\nname: 123\ndescription: d\n---\n\nB.\n")

        assert info.name == "123"

    @pytest.mark.parametrize("written", ["no", "yes", "true", "off"])
    def test_a_name_yaml_reads_as_a_boolean_stays_a_string(self, tmp_path, written):
        info = self._skill(tmp_path, f"b-{written}", f"---\nname: {written}\ndescription: d\n---\n\nB.\n")

        assert isinstance(info.name, str), f"`name: {written}` became {type(info.name).__name__}"

    def test_the_skill_can_be_found_by_the_name_it_declares(self, tmp_path):
        """The consequence, not just the type: registry lookups are by string."""
        info = self._skill(tmp_path, "numeric", "---\nname: 123\ndescription: d\n---\n\nB.\n")
        registry = {info.name: info}

        assert registry.get("123") is info

    def test_a_non_string_description_is_a_string(self, tmp_path):
        info = self._skill(tmp_path, "listy", "---\nname: n\ndescription: [a, b]\n---\n\nB.\n")

        assert isinstance(info.description, str)

    def test_a_block_scalar_description_keeps_all_of_its_text(self, tmp_path):
        """What the line splitter could not do: it kept only `>`."""
        info = self._skill(tmp_path, "blocky",
                           "---\nname: n\ndescription: >\n  line one\n  line two\n---\n\nB.\n")

        assert "line one" in info.description and "line two" in info.description


class TestTheBundledSkillsStillRead:
    """Converging on the stricter reader must not lose our own skills."""

    def test_every_bundled_skill_has_a_description(self):
        from pathlib import Path

        import connectonion
        from connectonion.cli.co_ai.skills.loader import _parse_skill_file

        root = Path(connectonion.__file__).parent
        bundled = sorted(root.rglob("SKILL.md"))

        assert bundled, "no bundled skills found — the glob is wrong"

        for path in bundled:
            info = _parse_skill_file(path)
            assert info.description, f"{path} lost its description"
