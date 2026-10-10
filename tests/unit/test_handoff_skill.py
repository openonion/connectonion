"""The handoff skill must name commands that exist and keep its safety rules."""

import re
from pathlib import Path

from typer.testing import CliRunner

from connectonion.cli.commands.copy_commands import SKILLS
from connectonion.cli.main import app

SKILL = Path(__file__).resolve().parents[2] / "connectonion" / "useful_skills" / "handoff" / "SKILL.md"


def test_handoff_is_a_copyable_single_file_skill():
    assert SKILLS["handoff"] == "handoff"
    assert sorted(path.name for path in SKILL.parent.iterdir()) == ["SKILL.md"]
    assert re.match(r"---\nname: handoff\ndescription: .+\n---\n", SKILL.read_text(encoding="utf-8"))


def test_every_co_command_the_skill_names_exists():
    body = SKILL.read_text(encoding="utf-8")
    for command in ("rem show", "email send", "email sent", "trust add",
                    "handoff send", "handoff status", "handoff contact", "handoff inbox", "handoff show", "handoff open"):
        assert f"co {command}" in body
        result = CliRunner().invoke(app, [*command.split(), "--help"])
        assert result.exit_code == 0, (command, result.output)


def test_an_invite_code_is_never_mailed_and_approval_comes_first():
    # A contact may EXEC on the host, and mail is forwarded.
    from connectonion.network.host.server import EXEC_REQUIRES
    assert "contact" in EXEC_REQUIRES
    body = SKILL.read_text(encoding="utf-8")
    assert "Never put an invite code in a handoff email" in body
    assert "Invite" not in body.split("Continue this with your AI")[1].split("```")[0]
    assert body.index("## 3. Audit") < body.index("## 4. Get the user's approval") < body.index("## 5a. Send by email")


def test_every_co_ai_session_can_find_the_handoff_skill():
    from connectonion.skills_catalog import default_skill_path
    assert default_skill_path("handoff") == SKILL
