"""Owner decision 2026-11-09: every model call has a level; level 1 is the
cheapest model, level 4 the strongest. `route.<stage>` still pins one stage.

#3099 (2026-11-17): no Astra; every stage but tag and investigation runs Sol at
low effort; investigation is a level of its own so it can be measured and set
apart; each level has its own effort."""

import yaml
import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem.config import STAGE_LEVELS, default_config, read_config, set_config
from connectonion.rem.inquiry import inquiry_routed, stage_config


LEVELS = {"level1": "gpt-6-luna", "level2": "gpt-6.1-sol", "level3": "gpt-6.1-sol", "level4": "gpt-6.1-sol",
          "investigate": "gpt-6.1-sol"}
EFFORTS = {"level1": "medium", "level2": "low", "level3": "low", "level4": "low", "investigate": "medium"}


def test_each_stage_resolves_to_its_levels_model_and_effort(tmp_path):
    config = read_config(tmp_path)
    assert config["models"] == LEVELS and config["efforts"] == EFFORTS
    for stage, level in STAGE_LEVELS.items():
        picked = stage_config(tmp_path, config, stage)
        assert (picked["model"], picked["effort"]) == (LEVELS[level], EFFORTS[level]), stage
    picked = {stage: (stage_config(tmp_path, config, stage)["model"], stage_config(tmp_path, config, stage)["effort"])
              for stage in ("tag", "sessions-summary", "translate", "maintain", "claim-audit", "investigate")}
    assert picked == {"tag": ("gpt-6-luna", "medium"), "sessions-summary": ("gpt-6.1-sol", "low"),
                      "translate": ("gpt-6.1-sol", "low"), "maintain": ("gpt-6.1-sol", "low"),
                      "claim-audit": ("gpt-6.1-sol", "low"), "investigate": ("gpt-6.1-sol", "medium")}


def test_no_stage_runs_astra_by_default(tmp_path):
    config = read_config(tmp_path)
    assert "gpt-6-astra" not in {stage_config(tmp_path, config, stage)["model"] for stage in STAGE_LEVELS}


def test_the_owners_saved_init_defaults_take_the_new_levels(tmp_path):
    """init wrote every default into config.yaml: Terra on level 2, Astra on level 4,
    medium effort and the fast tier. None was his choice, so none survives a read."""
    old = default_config()
    old.pop("efforts")
    old.update(effort="medium", speed="fast", models={"level1": "gpt-6-luna", "level2": "gpt-6.1-terra",
                                                      "level3": "gpt-6.1-sol", "level4": "gpt-6-astra"})
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(old))
    config = read_config(tmp_path)
    assert (config["models"], config["efforts"], config["speed"]) == (LEVELS, EFFORTS, "standard")


def test_an_owners_explicit_choices_are_kept(tmp_path):
    """A level he set, Luna included, and the fast tier he chose stay his."""
    config = set_config(tmp_path, ["models.level4", "gpt-6-astra", "models.investigate", "gpt-6-luna",
                                   "efforts.investigate", "max", "speed", "fast", "models.level2", "gpt-6.1-terra"])
    config = read_config(tmp_path)
    assert config["models"]["level4"] == "gpt-6-astra" and config["models"]["level2"] == "gpt-6.1-terra"
    assert stage_config(tmp_path, config, "investigate")["model"] == "gpt-6-luna"
    assert stage_config(tmp_path, config, "investigate")["effort"] == "max"
    assert config["speed"] == "fast"


def test_effort_sets_every_level_and_an_explicit_old_effort_still_applies(tmp_path):
    config = set_config(tmp_path, ["effort", "high", "efforts.level1", "low"])
    assert config["efforts"] == {**dict.fromkeys(EFFORTS, "high"), "level1": "low"}
    assert "effort" not in yaml.safe_load((tmp_path / "config.yaml").read_text())
    other = tmp_path / "other"
    old = default_config()
    old.pop("efforts")
    old["effort"] = "high"
    other.mkdir()
    (other / "config.yaml").write_text(yaml.safe_dump(old))
    (other / ".state").mkdir()
    (other / ".state" / "config-explicit.json").write_text('["effort"]')
    assert read_config(other)["efforts"] == dict.fromkeys(EFFORTS, "high")


def test_an_effort_codex_cannot_take_saves_nothing(tmp_path):
    from connectonion.rem.files import RemError
    with pytest.raises(RemError, match="max"):
        set_config(tmp_path, ["efforts.level2", "ultra"])
    assert read_config(tmp_path)["efforts"] == EFFORTS


def test_a_stage_outside_the_table_is_a_bug_not_a_silent_default(tmp_path):
    with pytest.raises(KeyError):
        stage_config(tmp_path, read_config(tmp_path), "no-such-stage")


def test_changing_a_level_moves_every_stage_on_it(tmp_path):
    config = set_config(tmp_path, ["models.level2", "gpt-6.1-terra"])
    assert stage_config(tmp_path, config, "translate")["model"] == "gpt-6.1-terra"
    assert stage_config(tmp_path, config, "tag")["model"] == "gpt-6-luna"
    assert stage_config(tmp_path, config, "maintain")["model"] == "gpt-6.1-sol"


def test_a_route_overrides_one_stage_only_and_does_not_start_inquiry(tmp_path):
    result = CliRunner().invoke(app, ["rem", "--root", str(tmp_path), "config", "set",
                                      "route.translate", "gpt-6.1-terra"])
    assert result.exit_code == 0, result.output
    config = read_config(tmp_path)
    assert stage_config(tmp_path, config, "translate")["model"] == "gpt-6.1-terra"
    assert stage_config(tmp_path, config, "topic")["model"] == "gpt-6.1-sol"
    assert not inquiry_routed(tmp_path)
    result = CliRunner().invoke(app, ["rem", "--root", str(tmp_path), "config", "set", "route.translate", "default"])
    assert result.exit_code == 0, result.output
    assert stage_config(tmp_path, read_config(tmp_path), "translate")["model"] == "gpt-6.1-sol"


def test_old_model_and_summary_keys_migrate_without_rewriting_the_file(tmp_path):
    old = default_config()
    old.pop("models")
    old.update(model="gpt-6-astra", models={"summary": "gpt-6.1-terra"})
    saved = yaml.safe_dump(old)
    (tmp_path / "config.yaml").write_text(saved)
    config = read_config(tmp_path)
    assert config["models"] == {"level1": "gpt-6.1-terra", "level2": "gpt-6.1-sol",
                                "level3": "gpt-6-astra", "level4": "gpt-6.1-sol", "investigate": "gpt-6-astra"}
    assert config["model"] == "gpt-6-astra"
    assert (tmp_path / "config.yaml").read_text() == saved


def test_the_owners_old_luna_notebook_gets_all_the_levels(tmp_path):
    old = default_config()
    old.pop("models")
    old["model"] = "gpt-6-luna"  # The owner's saved file, 2026-11-09.
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(old))
    assert read_config(tmp_path)["models"] == LEVELS


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


def test_status_shows_the_levels_their_efforts_and_their_stages(tmp_path):
    set_config(tmp_path, ["schedule.timezone", "UTC"])
    for command in ("config", "status"):
        output = CliRunner().invoke(app, ["rem", "--root", str(tmp_path), command]).output
        for level, model in LEVELS.items():
            label = level.replace("level", "level ")
            line = next((row for row in output.splitlines() if row.strip().startswith(label)), "")
            assert f"{model} at {EFFORTS[level]}" in line, (command, output)
        assert "translate" in output and "claim-audit" in output, output


def test_config_help_documents_the_levels():
    output = CliRunner().invoke(app, ["rem", "config", "--help"]).output
    assert "models.level1" in output and "models.level4" in output and "route.<stage>" in output
    assert "models.investigate" in output and "efforts.investigate" in output and "Sol at low" in output
