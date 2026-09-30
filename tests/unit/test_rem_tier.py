"""The job's shape comes from what the model did on a fixture page, not its name (#1847)."""

import re
from pathlib import Path

import pytest

from connectonion.rem import tier
from connectonion.rem.config import default_config, prepare
from connectonion.rem.files import Notebook, RemError, state_path, write_json


def _filled(prompt: str) -> str:
    """What a capable model makes of the fixture page it was handed: the fact, cited."""
    page = re.search(r"^# Ada Fixture$.*?^Investigation:[^\n]*$", prompt, re.M | re.S).group(0)
    source = re.search(r"gmail:[0-9a-f]{12}", prompt).group(0)
    return (page.replace("## Who they are\n- Unknown — not investigated yet",
                         "## Who they are\n- Head of research at Lovelace Instruments. [1]")
                .replace("- (none yet)", f"- [1] {source}")
                .replace("- Unknown — not investigated yet", "- Unknown"))


def _envelope(result: str) -> dict:
    return {"outcome": "natural", "result": result, "usage": {"input_tokens": 10}}


@pytest.fixture
def model(monkeypatch):
    """Fake models behind `co ai`; each records the prompts it was sent."""
    calls = []

    def agent(workspace, prompt, config, stage):   # drives tools: writes the file it is told to
        calls.append(prompt)
        candidate = re.search(r"NEW file (\S+candidate\.md)", prompt)
        if candidate:
            Path(candidate[1]).write_text(_filled(prompt), encoding="utf-8")
        return _envelope("Wrote the page.")

    def plain(workspace, prompt, config, stage):   # no tool loop: all it can do is reply
        calls.append(prompt)
        return _envelope("Here is the page:\n\n```markdown\n" + _filled(prompt) + "\n```")

    def broken(workspace, prompt, config, stage):   # neither writes nor replies with a page
        calls.append(prompt)
        return _envelope("I cannot help with that.")

    def use(kind):
        monkeypatch.setattr("connectonion.rem.runner.run_task", {"agent": agent, "plain": plain,
                                                                 "broken": broken}[kind])
        return calls
    return use


def test_a_model_that_drives_tools_is_the_agent_tier(model):
    calls = model("agent")
    result = tier.check(default_config())
    assert result["tier"] == "agent" and result["agent"]["passed"]
    assert len(calls) == 1


def test_a_model_that_cannot_drive_tools_is_the_summary_tier(model):
    calls = model("plain")
    result = tier.check(default_config())
    assert result["agent"]["passed"] is False
    assert result["tier"] == "summary" and result["summary"]["passed"]
    assert len(calls) == 2


def test_the_fixture_page_is_filled_in_both_tiers(model):
    model("agent")
    assert tier.attempt(default_config(), "agent") == []
    model("plain")
    assert tier.attempt(default_config(), "summary") == []


def test_the_summary_tier_gathers_in_python_and_makes_one_call_for_the_page(model):
    calls = model("plain")
    assert tier.attempt(default_config(), "summary") == []
    assert len(calls) == 1
    # The mail was fetched by Python and handed over whole; the model is told to reply, not to use tools.
    assert "twelve units" in calls[0] and "Do not call tools" in calls[0]
    assert "your reply is that file" in calls[0]


def test_a_model_that_fills_no_page_is_not_given_a_tier(tmp_path, model):
    model("broken")
    config = default_config()
    with pytest.raises(RemError) as error:
        tier.check_and_record(tmp_path, config)
    assert "neither tier" in str(error.value)
    assert f"`co rem config set model {config['model']}`" in str(error.value)
    assert tier.current(tmp_path, config) == tier.UNCHECKED


def test_the_recorded_tier_holds_only_for_the_model_it_was_measured_on(tmp_path, model):
    model("plain")
    config = default_config()
    entry = tier.check_and_record(tmp_path, config)
    assert entry["model"] == config["model"] and entry["checked_at"]
    assert tier.current(tmp_path, config) == "summary"
    other = {**config, "model": "gpt-7-nova"}
    assert tier.current(tmp_path, other) == "agent"
    described = tier.describe(tmp_path, other)
    assert described["checked"] is False and config["model"] in described["note"]


def test_an_unchecked_notebook_runs_as_the_agent_tier(tmp_path):
    assert tier.current(tmp_path, default_config()) == "agent"
    assert tier.describe(tmp_path, default_config())["note"].startswith("never checked")


def test_a_summary_tier_extraction_takes_the_reply_as_its_notes(tmp_path, monkeypatch):
    from connectonion.rem.extract import run_extract
    prepare(tmp_path)
    config = default_config()
    write_json(state_path(tmp_path, tier.RECORD), {"tier": "summary", "runner": config["runner"],
                                                   "model": config["model"]})
    prompts = []
    monkeypatch.setattr("connectonion.rem.extract.run_task",
                        lambda workspace, prompt, cfg, stage: prompts.append(prompt) or _envelope("- Ada leads research."))
    items = [{"role": "other", "source": "gmail:abc", "timestamp": "2026-09-01T00:00:00+00:00", "text": "hi"}]
    assert run_extract(items, config, "gmail", root=tmp_path)["notes"] == "- Ada leads research."
    assert "do not call tools" in prompts[0]


def test_a_summary_tier_project_page_is_handed_its_files(tmp_path):
    from connectonion.rem.investigate import project_file_texts
    readme = tmp_path / "README.md"
    readme.write_text("Orbit is a scheduler. " * 200)
    [item] = project_file_texts([str(readme)])
    assert item["source"] == str(readme) and item["text"].startswith("Orbit is a scheduler.")
    assert item["text"].endswith("[truncated]")


def test_a_reply_wrapped_in_prose_and_a_fence_is_still_the_page():
    page = "# Ada\n\n## Contact\n- Email: a@b.c\n"
    assert tier.page_from_reply(f"Sure.\n\n```markdown\n{page}```") == page
    assert tier.page_from_reply(page) == page
