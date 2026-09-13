"""The harness axis: which loop runs the task, and what the envelope reports."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

# The package __init__ re-exports the `codex` function, which shadows the
# submodule of the same name — so both the dotted monkeypatch path and a plain
# `import ... as` hand back the function. sys.modules still holds the module.
import sys

import connectonion.useful_tools.codex  # noqa: F401  (registers the module)

codex_module = sys.modules["connectonion.useful_tools.codex"]

from connectonion.cli.co_ai import harness as harness_mod
from connectonion.cli.commands import ai_commands


def _skill(tmp_path, name="demo", body="# Demo\nDo the demo thing."):
    directory = tmp_path / name
    directory.mkdir()
    path = directory / "SKILL.md"
    path.write_text(body, encoding="utf-8")
    return SimpleNamespace(
        name=name, path=path, requirements=None, load_content=lambda: body
    )


@pytest.fixture
def registry(monkeypatch):
    """Install a fake skill registry the way the loader would have."""
    from connectonion.cli.co_ai.skills import loader

    entries = {}
    monkeypatch.setattr(loader, "SKILLS_REGISTRY", entries)
    monkeypatch.setattr(loader, "get_skill", entries.get)
    monkeypatch.setattr(loader, "load_skills", lambda: entries)
    return entries


def test_our_model_names_are_refused_for_a_delegated_harness():
    problem = harness_mod.validate("codex", "co/gemini-3.8-flash")
    assert "co/gemini-3.8-flash" in problem and "codex" in problem
    # The message must name a model that would work, not just say no.
    assert "gpt-5.6-luna" in problem


def test_each_delegate_is_offered_its_own_models_not_another_delegates():
    assert "opus" in harness_mod.validate("claude-code", "ollama/qwen3")
    assert "gpt-5.6-luna" not in harness_mod.validate("claude-code", "ollama/qwen3")


def test_an_explicit_model_equal_to_our_default_is_still_an_explicit_model():
    """The bug a default-comparison hides: typing our default is not silence."""
    from connectonion.core.usage import DEFAULT_MODEL

    assert harness_mod.validate("codex", DEFAULT_MODEL) is not None
    assert harness_mod.validate("codex", None) is None


def test_unknown_harness_lists_the_ones_that_exist():
    problem = harness_mod.validate("nope", None)
    for name in harness_mod.HARNESSES:
        assert name in problem


def test_our_harness_accepts_any_model():
    assert harness_mod.validate("ours", "co/gemini-3.8-flash") is None
    assert harness_mod.validate("ours", "ollama/qwen3") is None


def test_a_slash_prompt_hands_over_the_instructions_not_the_name(tmp_path, registry):
    """A delegate cannot resolve `/demo`: nothing registers .co/skills with it."""
    registry["demo"] = _skill(tmp_path)

    expanded = harness_mod.expand_skill("/demo run it twice")

    assert "Do the demo thing." in expanded          # the body travelled
    assert str(tmp_path / "demo") in expanded        # so did where it lives
    assert "run it twice" in expanded                # and the arguments
    assert expanded != "/demo run it twice"


def test_a_skill_without_arguments_carries_no_empty_argument_section(tmp_path, registry):
    registry["demo"] = _skill(tmp_path)
    assert "## Arguments" not in harness_mod.expand_skill("/demo")
    assert "## Arguments" in harness_mod.expand_skill("/demo  something ")


def test_a_plain_prompt_is_handed_over_unchanged(registry):
    assert harness_mod.expand_skill("fix the failing tests") == "fix the failing tests"


def test_a_missing_skill_names_what_is_installed(tmp_path, registry):
    registry["demo"] = _skill(tmp_path)
    with pytest.raises(ValueError) as caught:
        harness_mod.expand_skill("/absent do it")
    assert "absent" in str(caught.value) and "demo" in str(caught.value)


def test_a_delegate_that_does_not_answer_in_json_becomes_an_error_not_a_crash(monkeypatch):
    monkeypatch.setattr(
        codex_module, "codex",
        lambda **kwargs: "codex: command not found",
    )
    answer = harness_mod.run("codex", "do it", "")
    assert answer["outcome"] == "error"
    assert "command not found" in answer["error"]


def test_a_nonzero_exit_is_a_failure_even_without_an_error_field(monkeypatch):
    monkeypatch.setattr(
        codex_module, "codex",
        lambda **kwargs: json.dumps({"last_message": "partial", "exit_code": 3}),
    )
    answer = harness_mod.run("codex", "do it", "")
    assert answer["outcome"] == "error" and "3" in answer["error"]


def test_a_completed_delegate_run_reports_its_own_usage(monkeypatch):
    monkeypatch.setattr(
        codex_module, "codex",
        lambda **kwargs: json.dumps({
            "last_message": "done", "exit_code": 0, "session_id": "t1",
            "usage": {"input_tokens": 12, "output_tokens": 3},
        }),
    )
    answer = harness_mod.run("codex", "do it", "")
    assert answer == {"result": "done", "outcome": "natural", "error": None,
                      "usage": {"input_tokens": 12, "output_tokens": 3},
                      "session_id": "t1"}


def test_the_requested_model_reaches_the_delegate(monkeypatch):
    seen = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return json.dumps({"last_message": "ok", "exit_code": 0})

    monkeypatch.setattr(codex_module, "codex", fake)
    harness_mod.run("codex", "do it", "gpt-5.6-luna", cwd="/tmp", timeout=30)
    assert seen["model"] == "gpt-5.6-luna"
    assert seen["cwd"] == "/tmp" and seen["timeout"] == 30
    # Nothing is watching a delegated one-shot; a manual approval would hang it.
    assert seen["approval"] == "auto"


def test_delegating_without_a_prompt_is_refused_before_a_process_starts(capsys):
    with pytest.raises(typer.Exit):
        ai_commands.handle_ai(harness="codex", json_output=True)
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["outcome"] == "error"
    assert "one-shot prompt" in envelope["error"]


def _trace_turn(turn, tokens):
    return [
        {"type": "user_input", "turn": turn},
        {"type": "llm_result", "usage": {
            "input_tokens": tokens, "output_tokens": 1, "cost": 0.5,
            "cached_tokens": 0, "cache_write_tokens": 0, "total_tokens": tokens + 1,
        }},
    ]


def test_the_envelope_bills_this_turn_only_not_the_resumed_history():
    """A resumed run carries the earlier turns' llm_result entries in one list."""
    agent = SimpleNamespace(current_session={
        "turn": 2, "trace": _trace_turn(1, 1000) + _trace_turn(2, 7),
    })
    usage = ai_commands._turn_usage(agent)
    assert usage["input_tokens"] == 7
    assert usage["cost"] == 0.5


def test_a_turn_that_measured_nothing_reports_nothing_rather_than_zero():
    """An all-zero usage would read as 'this run was free'."""
    agent = SimpleNamespace(current_session={"turn": 1, "trace": [
        {"type": "user_input", "turn": 1}, {"type": "tool_result"},
    ]})
    assert ai_commands._turn_usage(agent) is None
    assert ai_commands._turn_usage(None) is None


def test_a_delegate_reporting_no_usage_says_nothing_rather_than_zero(monkeypatch):
    """Codex answers `usage: {}` on a small turn; `{}` must not read as free."""
    monkeypatch.setattr(
        codex_module, "codex",
        lambda **kwargs: json.dumps({"last_message": "ok", "exit_code": 0, "usage": {}}),
    )
    assert harness_mod.run("codex", "do it", "")["usage"] is None


def test_the_sandbox_level_reaches_codex(monkeypatch):
    seen = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return json.dumps({"last_message": "ok", "exit_code": 0})

    monkeypatch.setattr(codex_module, "codex", fake)
    harness_mod.run("codex", "do it", "", sandbox="danger-full-access")
    assert seen["sandbox"] == "danger-full-access"


def test_sandbox_is_refused_for_a_harness_that_has_no_such_setting():
    problem = harness_mod.validate_sandbox("claude-code", "danger-full-access")
    assert "claude-code" in problem and "own permissions" in problem
    # The default is not a request, so it never trips this.
    assert harness_mod.validate_sandbox("claude-code", harness_mod.DEFAULT_SANDBOX) is None


def test_an_unknown_sandbox_lists_the_real_ones():
    problem = harness_mod.validate_sandbox("codex", "wide-open")
    for level in harness_mod.SANDBOXES:
        assert level in problem
