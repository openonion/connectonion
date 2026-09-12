"""
LLM-Note: The co-inbox skill and `co feishu --help` must list the same verbs.
A skill naming a command that does not exist costs an agent a round trip; a
command the skill never mentions is one it will not find. Both directions, as
cli-skill-design requires — this is the check that keeps them from drifting.
"""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app

SKILL = (Path(__file__).resolve().parents[2]
         / "connectonion/useful_skills/co-inbox/SKILL.md")

# Words that follow `co feishu` in a sentence without being verbs.
NOT_VERBS = {"is", "the", "and"}

runner = CliRunner()


def cli_verbs() -> set:
    result = runner.invoke(app, ["feishu", "--help"])
    assert result.exit_code == 0, result.output
    found = set(re.findall(r"^\s*│?\s*([a-z][a-z-]+)\s{2,}", result.output, re.M))
    return found - {"options", "usage", "commands"}


def skill_verbs() -> set:
    text = SKILL.read_text(encoding="utf-8")
    found = set(re.findall(r"co (?:feishu|lark) ([a-z][a-z-]+)", text))
    return found - NOT_VERBS


class TestTheyAgree:
    def test_the_skill_documents_every_command(self):
        missing = sorted(cli_verbs() - skill_verbs())
        assert missing == [], f"in the CLI, undocumented: {missing}"

    def test_the_skill_invents_no_command(self):
        invented = sorted(skill_verbs() - cli_verbs())
        assert invented == [], f"named by the skill, absent from --help: {invented}"

    def test_every_co_auth_the_skill_names_exists(self):
        text = SKILL.read_text(encoding="utf-8")
        named = set(re.findall(r"co auth ([a-z]+)", text))
        listed = runner.invoke(app, ["auth", "--help"]).output
        for service in sorted(named):
            assert service in listed, f"skill names `co auth {service}`, which --help omits"


class TestItSaysTheThingsThatMatter:
    def test_it_opens_with_the_read_the_output_rule(self):
        # Required whenever a failure can exit 0; `consume` reports a failing
        # command on stderr and keeps going.
        text = SKILL.read_text(encoding="utf-8")
        assert "read the output, not just the exit code" in text.lower()

    def test_it_carries_an_exit_code_table_whose_right_column_is_a_command(self):
        text = SKILL.read_text(encoding="utf-8")
        assert "| 124 |" in text and "| 3 |" in text
        for code, command in (("3", "co auth feishu"), ("124", "co feishu ls")):
            row = next(line for line in text.splitlines() if line.startswith(f"| {code} |"))
            assert command in row, f"exit {code} names no command: {row}"

    def test_it_does_not_claim_the_gate_that_has_not_passed(self):
        # The honesty rule: document only what has been run.
        text = SKILL.read_text(encoding="utf-8")
        assert "does not guarantee delivery across a reconnect" in text
