"""#2280: docs/cli/auth.md still promised the pre-#1444 behaviour (a project
.env updated too, local .co preferred) while the code writes one selected
file, global by default. A reader then changes directory to "fix" the account."""

from pathlib import Path

AUTH_DOC = Path(__file__).resolve().parents[2] / "docs" / "cli" / "auth.md"


def test_the_auth_guide_makes_no_local_first_promise():
    text = " ".join(AUTH_DOC.read_text(encoding="utf-8").split())

    assert "it's updated too" not in text
    assert "an existing project `.env`" not in text
    assert "prefers local `.co`" not in text


def test_the_auth_guide_shows_how_to_choose_a_project_file():
    assert "co --env-file ./.env auth google" in AUTH_DOC.read_text(encoding="utf-8")
