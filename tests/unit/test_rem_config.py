

def test_a_notebook_made_with_old_defaults_runs_with_todays(tmp_path):
    """A notebook from 2026-09-20 kept gpt-5.3-codex-spark, which ChatGPT logins
    refuse, and failed every scheduled run for four days (#1714)."""
    import yaml
    from connectonion.rem.config import default_config, prepare, read_config
    prepare(tmp_path)
    old = default_config()
    old["model"] = "gpt-5.3-codex-spark"
    old["limits"].update(timeout_seconds=600, extract_chars_per_batch=300000, runner_calls_per_day=6)
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(old))
    config, now = read_config(tmp_path), default_config()
    assert config["model"] == now["model"]
    assert {k: config["limits"][k] for k in ("timeout_seconds", "extract_chars_per_batch", "runner_calls_per_day")} \
        == {k: now["limits"][k] for k in ("timeout_seconds", "extract_chars_per_batch", "runner_calls_per_day")}


def test_a_value_the_owner_set_is_kept_even_if_it_was_once_a_default(tmp_path):
    from connectonion.rem.config import prepare, read_config, set_config
    prepare(tmp_path)
    set_config(tmp_path, ["limits.timeout_seconds", "600"])
    assert read_config(tmp_path)["limits"]["timeout_seconds"] == 600
