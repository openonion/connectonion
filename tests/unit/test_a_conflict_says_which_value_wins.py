"""`co status` names a credential conflict without saying which value is used.

The panel reports:

    Gemini   GEMINI_API_KEY   conflict   process environment + <project>/.env

Both true, and it stops one word short of the answer. The operator is looking at
this panel *because* something is using the wrong key, and it does not tell them
which one that is — so the natural guess is that the project's own `.env` wins,
being the more specific of the two.

It does not. `dotenv.load_dotenv()` does not override a variable already in the
environment, so the process environment wins. Measured:

    .env says: project-value | environment says: environment-value
    the value an agent would use: environment-value

The information was already there: `_credential_sources` returns its sources in
precedence order, process environment first, and `found` preserves it. So the
first source listed is the winner and nothing said so.

Marked rather than reordered or reworded — the list stays complete, because
"where else is this defined" is the other half of what the operator came for.
"""

from pathlib import Path

import pytest

from connectonion.cli.commands.status_commands import _credential_rows


def _row(rows, name):
    return next(r for r in rows if r["credential"] == name)


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".co").mkdir()
    return tmp_path


class TestAConflictNamesTheWinner:

    def test_the_environment_is_marked_when_it_wins(self, project):
        (project / ".env").write_text("GEMINI_API_KEY=from-dot-env\n", encoding="utf-8")

        rows = _credential_rows(project_dir=project, home=project / "home",
                                environ={"GEMINI_API_KEY": "from-environment"})
        row = _row(rows, "GEMINI_API_KEY")

        assert row["status"] == "conflict"
        assert "process environment (used)" in row["source"], row["source"]

    def test_the_other_places_are_still_listed(self, project):
        """Where else it is defined is the other half of the question."""
        (project / ".env").write_text("GEMINI_API_KEY=from-dot-env\n", encoding="utf-8")

        rows = _credential_rows(project_dir=project, home=project / "home",
                                environ={"GEMINI_API_KEY": "from-environment"})

        assert "<project>/.env" in _row(rows, "GEMINI_API_KEY")["source"]

    def test_the_file_is_marked_when_it_is_the_only_one_loaded(self, project):
        """No environment value: the highest-precedence source present wins."""
        (project / ".env").write_text("GEMINI_API_KEY=from-dot-env\n", encoding="utf-8")
        home = project / "home"
        (home / ".co").mkdir(parents=True)
        (home / ".co" / "keys.env").write_text("GEMINI_API_KEY=from-home\n",
                                               encoding="utf-8")

        row = _row(_credential_rows(project_dir=project, home=home, environ={}),
                   "GEMINI_API_KEY")

        assert row["status"] == "conflict"
        assert "<project>/.env (used)" in row["source"], row["source"]


class TestNothingElseChanges:

    def test_one_source_is_not_marked(self, project):
        """Nothing to disambiguate — a mark would be noise."""
        rows = _credential_rows(project_dir=project, home=project / "home",
                                environ={"GEMINI_API_KEY": "only-here"})
        row = _row(rows, "GEMINI_API_KEY")

        assert row["status"] == "configured"
        assert "(used)" not in row["source"]

    def test_the_same_value_twice_is_not_a_conflict(self, project):
        """Defined in two places with one value: still not a conflict, and
        still nothing to choose between."""
        (project / ".env").write_text("GEMINI_API_KEY=same\n", encoding="utf-8")

        row = _row(_credential_rows(project_dir=project, home=project / "home",
                                    environ={"GEMINI_API_KEY": "same"}),
                   "GEMINI_API_KEY")

        assert row["status"] != "conflict"
        assert "(used)" not in row["source"]

    def test_missing_is_untouched(self, project):
        row = _row(_credential_rows(project_dir=project, home=project / "home",
                                    environ={}), "GEMINI_API_KEY")

        assert row["status"] == "missing"
        assert row["source"] == "—"
