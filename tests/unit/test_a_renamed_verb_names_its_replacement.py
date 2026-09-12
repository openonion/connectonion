"""
LLM-Note: `serve` became `consume`. Click's own suggestion works on edit
distance and offers nothing for a rename, so a reader of the 1.8.5b1 notes
would get "No such command" and no way forward. This pins the answer instead.
"""

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.typer_groups import _OneSuggestion

runner = CliRunner()


def said(result) -> str:
    """What the caller sees. A UsageError raised before a command runs is
    carried on the result rather than rendered into output by the runner."""
    return result.output + str(result.exception or "")


class TestTheOldNameAnswers:
    @pytest.mark.parametrize("provider", ["feishu", "lark"])
    def test_it_names_the_new_verb(self, provider):
        result = runner.invoke(app, [provider, "serve", "--", "echo", "x"])
        assert result.exit_code != 0
        assert "consume" in said(result)
        assert f"co {provider} consume" in said(result)

    def test_it_does_not_run_anything(self, provider="feishu"):
        # A rename hint that ran the command anyway would be worse than an
        # error: the caller would never learn the name changed.
        result = runner.invoke(app, [provider, "serve", "--", "echo", "x"])
        assert "renamed" in said(result).lower()


class TestEverythingElseIsUnchanged:
    def test_a_real_typo_still_gets_one_suggestion(self):
        result = runner.invoke(app, ["skil"])
        assert said(result).lower().count("did you mean") <= 1

    def test_an_unknown_verb_is_still_unknown(self):
        result = runner.invoke(app, ["feishu", "nonsense"])
        assert result.exit_code != 0
        assert "renamed" not in said(result).lower()

    def test_the_map_only_names_verbs_that_exist(self):
        # A rename entry pointing at a command nobody registered would answer
        # a dead end with another dead end.
        for old, new in _OneSuggestion.RENAMED.items():
            result = runner.invoke(app, ["feishu", new, "--help"])
            assert result.exit_code == 0, f"{old} points at {new}, which does not run"
