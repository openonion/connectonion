"""Owner decision 2026-11-09: every model call has a level; level 1 is the
cheapest model, level 4 the strongest. `route.<stage>` still pins one stage."""

import yaml
import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem.config import STAGE_LEVELS, default_config, read_config, set_config
from connectonion.rem.inquiry import inquiry_routed, stage_config


LEVELS = {1: "gpt-6-luna", 2: "gpt-6.1-terra", 3: "gpt-6.1-sol", 4: "gpt-6-astra"}


def test_each_stage_resolves_to_its_levels_model(tmp_path):
    config = read_config(tmp_path)
    assert config["models"] == {f"level{n}": model for n, model in LEVELS.items()}
    for stage, level in STAGE_LEVELS.items():
        assert stage_config(tmp_path, config, stage)["model"] == LEVELS[level], stage
    picked = {stage: stage_config(tmp_path, config, stage)["model"]
              for stage in ("sessions-summary", "translate", "maintain", "claim-audit")}
    assert picked == {"sessions-summary": "gpt-6-luna", "translate": "gpt-6.1-terra",
                      "maintain": "gpt-6.1-sol", "claim-audit": "gpt-6-astra"}


def test_a_stage_outside_the_table_is_a_bug_not_a_silent_default(tmp_path):
    with pytest.raises(KeyError):
        stage_config(tmp_path, read_config(tmp_path), "no-such-stage")


def test_changing_a_level_moves_every_stage_on_it(tmp_path):
    config = set_config(tmp_path, ["models.level2", "gpt-6.1-sol"])
    assert stage_config(tmp_path, config, "translate")["model"] == "gpt-6.1-sol"
    assert stage_config(tmp_path, config, "sessions-summary")["model"] == "gpt-6-luna"


def test_a_route_overrides_one_stage_only_and_does_not_start_inquiry(tmp_path):
    result = CliRunner().invoke(app, ["rem", "--root", str(tmp_path), "config", "set",
                                      "route.translate", "gpt-6.1-sol"])
    assert result.exit_code == 0, result.output
    config = read_config(tmp_path)
    assert stage_config(tmp_path, config, "translate")["model"] == "gpt-6.1-sol"
    assert stage_config(tmp_path, config, "topic")["model"] == "gpt-6-luna"
    assert not inquiry_routed(tmp_path)
    result = CliRunner().invoke(app, ["rem", "--root", str(tmp_path), "config", "set", "route.translate", "default"])
    assert result.exit_code == 0, result.output
    assert stage_config(tmp_path, read_config(tmp_path), "translate")["model"] == "gpt-6.1-terra"


def test_old_model_and_summary_keys_migrate_without_rewriting_the_file(tmp_path):
    old = default_config()
    old.pop("models")
    old.update(model="gpt-6-astra", models={"summary": "gpt-6.1-terra"})
    saved = yaml.safe_dump(old)
    (tmp_path / "config.yaml").write_text(saved)
    config = read_config(tmp_path)
    assert config["models"] == {"level1": "gpt-6.1-terra", "level2": "gpt-6.1-terra",
                                "level3": "gpt-6-astra", "level4": "gpt-6-astra"}
    assert config["model"] == "gpt-6-astra"
    assert (tmp_path / "config.yaml").read_text() == saved


def test_the_owners_old_luna_notebook_gets_all_four_levels(tmp_path):
    old = default_config()
    old.pop("models")
    old["model"] = "gpt-6-luna"  # The owner's saved file, 2026-11-09.
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(old))
    assert read_config(tmp_path)["models"] == {f"level{n}": model for n, model in LEVELS.items()}


def test_an_old_claude_notebook_keeps_its_one_model_on_every_level(tmp_path):
    old = default_config()
    old.pop("models")
    old.update(runner="claude-code", model="claude-sonnet-5-5")
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(old))
    assert set(read_config(tmp_path)["models"].values()) == {"claude-sonnet-5-5"}


def test_old_setting_names_still_set_their_level(tmp_path):
    config = set_config(tmp_path, ["model", "gpt-6-astra", "models.summary", "gpt-6.1-terra"])
    assert config["models"]["level3"] == config["model"] == "gpt-6-astra"
    assert config["models"]["level1"] == "gpt-6.1-terra"
    saved = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert "model" not in saved and saved["models"]["level3"] == "gpt-6-astra"


def test_a_level_change_leaves_a_pending_tasks_config_digest_unchanged(tmp_path):
    from connectonion.rem.native import _config_hash
    old = default_config()
    old.pop("models")
    old.update(model="gpt-6.1-sol", models={"summary": "gpt-6-luna"})
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(old))
    before = _config_hash(old)
    assert _config_hash(read_config(tmp_path)) == before
    for key, value in (("models.level1", "gpt-6.1-terra"), ("models.level4", "gpt-6.1-sol"), ("model", "gpt-6-astra")):
        assert _config_hash(set_config(tmp_path, [key, value])) == before


def test_status_shows_the_four_levels_and_their_stages(tmp_path):
    set_config(tmp_path, ["schedule.timezone", "UTC"])
    for command in ("config", "status"):
        output = CliRunner().invoke(app, ["rem", "--root", str(tmp_path), command]).output
        for level, model in LEVELS.items():
            line = next((row for row in output.splitlines() if f"level {level}" in row.lower()), "")
            assert model in line, (command, output)
        assert "translate" in output and "claim-audit" in output, output


def test_config_help_documents_the_levels():
    output = CliRunner().invoke(app, ["rem", "config", "--help"]).output
    assert "models.level1" in output and "models.level4" in output and "route.<stage>" in output
