"""
LLM-Note: Tests for `co browser config` and the configured default engine.
The setting lives in the selected env file as CO_BROWSER_ENGINE, so `co env`
answers where it came from; `--engine` overrides it for one run, in both
directions. Also `wtf` as the paid engine's name, with `onion` as the alias.
"""

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.useful_tools.browser_tools import engine as engine_module

runner = CliRunner()


class TestTheNameIsWtf:
    def test_wtf_is_the_paid_engine(self):
        assert engine_module.WTF == "wtf"

    def test_onion_still_resolves_to_it(self):
        assert engine_module.normalize_mode("onion") == engine_module.WTF

    def test_the_modes_a_person_may_type(self):
        assert set(engine_module.ACCEPTED_MODES) == {"auto", "system", "wtf", "onion"}

    def test_an_unknown_name_is_refused(self):
        with pytest.raises(ValueError):
            engine_module.normalize_mode("chrome")


class TestTheConfiguredDefault:
    def test_unset_means_system_chrome(self, monkeypatch):
        monkeypatch.delenv("CO_BROWSER_ENGINE", raising=False)
        assert engine_module.configured_mode() is None

    def test_it_reads_the_env_file_value(self, monkeypatch):
        monkeypatch.setenv("CO_BROWSER_ENGINE", "wtf")
        assert engine_module.configured_mode() == "wtf"

    def test_the_old_spelling_is_accepted_there_too(self, monkeypatch):
        monkeypatch.setenv("CO_BROWSER_ENGINE", "onion")
        assert engine_module.configured_mode() == "wtf"

    def test_a_nonsense_value_is_ignored_rather_than_fatal(self, monkeypatch):
        # A typo in a config file must not make every browser command fail.
        monkeypatch.setenv("CO_BROWSER_ENGINE", "definitely-not-an-engine")
        assert engine_module.configured_mode() is None

    def test_case_and_spacing_do_not_matter(self, monkeypatch):
        monkeypatch.setenv("CO_BROWSER_ENGINE", "  WTF  ")
        assert engine_module.configured_mode() == "wtf"


class TestWhichOneWins:
    def test_a_flag_beats_the_config(self, monkeypatch):
        monkeypatch.setenv("CO_BROWSER_ENGINE", "wtf")
        assert engine_module.effective_mode("system") == "system"

    def test_the_config_is_used_when_no_flag_was_given(self, monkeypatch):
        monkeypatch.setenv("CO_BROWSER_ENGINE", "wtf")
        assert engine_module.effective_mode(None) == "wtf"

    def test_with_neither_it_is_auto(self, monkeypatch):
        monkeypatch.delenv("CO_BROWSER_ENGINE", raising=False)
        assert engine_module.effective_mode(None) == "auto"

    def test_system_can_always_be_asked_for(self, monkeypatch):
        # There has to be a way to not spend money that needs no file edit.
        monkeypatch.setenv("CO_BROWSER_ENGINE", "wtf")
        assert engine_module.effective_mode("system") == "system"


class TestAConfiguredPaidSessionSaysSo:
    def test_the_reason_distinguishes_it_from_a_requested_one(self):
        # When an unexpected charge shows up, the first question is which
        # invocations were a standing choice rather than a request.
        assert engine_module.Reason.WTF_CONFIGURED != engine_module.Reason.WTF_READY


class TestTheCommand:
    def test_config_is_a_browser_subcommand(self):
        result = runner.invoke(app, ["browser", "config", "--help"])
        assert result.exit_code == 0, result.output

    def test_with_no_argument_it_shows_the_default_and_where_it_came_from(self, monkeypatch):
        monkeypatch.setenv("CO_BROWSER_ENGINE", "wtf")
        result = runner.invoke(app, ["browser", "config"])
        assert result.exit_code == 0, result.output
        assert "wtf" in result.output.lower()

    def test_unset_says_so_rather_than_printing_nothing(self, monkeypatch):
        monkeypatch.delenv("CO_BROWSER_ENGINE", raising=False)
        result = runner.invoke(app, ["browser", "config"])
        assert result.exit_code == 0
        assert "system" in result.output.lower()

    def test_a_bad_value_is_refused_with_the_ones_that_work(self):
        result = runner.invoke(app, ["browser", "config", "chrome"])
        assert result.exit_code == 2
        assert "wtf" in result.output.lower() and "system" in result.output.lower()

    def test_it_names_what_a_paid_default_costs_before_writing_one(self, monkeypatch, tmp_path):
        written = {}
        monkeypatch.setattr("connectonion.cli.commands.browser_config.upsert_env",
                            lambda path, values: written.update(values))
        result = runner.invoke(app, ["browser", "config", "wtf"])
        assert result.exit_code == 0, result.output
        assert written.get("CO_BROWSER_ENGINE") == "wtf"
        assert "paid" in result.output.lower() or "charge" in result.output.lower()
