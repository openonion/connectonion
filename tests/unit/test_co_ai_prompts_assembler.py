"""Tests for prompt assembler utilities."""
"""
LLM-Note: Tests for co ai prompts assembler

What it tests:
- Co Ai Prompts Assembler functionality

Components under test:
- Module: co_ai_prompts_assembler
"""


from pathlib import Path

import pytest

from connectonion.cli.co_ai.tools import ask_user
from connectonion.cli.co_ai.prompts.assembler import (
    PromptContext,
    interpolate,
    assemble_prompt,
    load_reminder,
    load_agent_prompt,
)


PROMPTS_DIR = Path(__file__).resolve().parents[2] / "connectonion" / "cli" / "co_ai" / "prompts"


def flatten(text: str) -> str:
    """Collapse whitespace so phrase assertions survive markdown re-wrapping.

    The prompts are hard-wrapped at ~78 columns; without this, reflowing a
    paragraph fails tests that have nothing to do with the change.
    """
    return " ".join(text.split())


def test_interpolate_basic_and_defaults():
    text = "Hello ${NAME}, ${MISSING or \"default\"}!"
    out = interpolate(text, {"NAME": "World"})
    assert out == "Hello World, default!"


def test_prompt_context_and_assemble(tmp_path):
    prompts = tmp_path / "prompts"
    (prompts / "connectonion" / "examples").mkdir(parents=True)
    (prompts / "tools").mkdir(parents=True)
    (prompts / "reminders").mkdir(parents=True)
    (prompts / "agents").mkdir(parents=True)

    (prompts / "main.md").write_text("Hello ${NAME}", encoding="utf-8")
    (prompts / "workflow.md").write_text("Tool? ${has_tool(\"foo\") ? \"yes\" : \"no\"}", encoding="utf-8")
    (prompts / "connectonion" / "index.md").write_text("Index", encoding="utf-8")
    (prompts / "connectonion" / "examples" / "ex.md").write_text("Example", encoding="utf-8")
    (prompts / "tools" / "foo.md").write_text("Foo tool is ${FOO_TOOL_NAME}", encoding="utf-8")
    (prompts / "reminders" / "plan_mode.md").write_text("Plan for ${PROJECT}", encoding="utf-8")
    (prompts / "agents" / "explore.md").write_text("Explore ${PROJECT}", encoding="utf-8")

    def foo():
        return "ok"

    out = assemble_prompt(
        prompts_dir=str(prompts),
        tools=[foo],
        extra_vars={"NAME": "World", "PROJECT": "Test"},
    )

    assert "Hello World" in out
    assert "Foo tool is foo" in out
    # workflow.md, index, and examples are loaded on-demand by system_reminder plugin,
    # not during base prompt assembly
    assert "Tool? yes" not in out
    assert "Index" not in out
    assert "Example" not in out

    reminder = load_reminder(str(prompts), "plan_mode", extra_vars={"PROJECT": "Test"})
    assert reminder.startswith("<system-reminder>")
    assert "Plan for Test" in reminder

    agent_prompt = load_agent_prompt(str(prompts), "explore", extra_vars={"PROJECT": "Test"})
    assert agent_prompt == "Explore Test"


def test_login_prompt_uses_ask_user_and_screenshot():
    prompt = flatten(assemble_prompt(
        prompts_dir=str(PROMPTS_DIR),
        tools=[
            ask_user,
        ],
    ))

    # Login instructions live with the browser, not with the coding role — an
    # agent that only posts to a website still has to be able to log in.
    assert "Do not refuse" in prompt
    assert "help me login" in prompt
    assert "log in" in prompt
    assert "sign in" in prompt
    # The login flow now goes through the CLI, not in-process browser tools.
    assert "co browser go_to" in prompt
    assert "co browser take_screenshot" in prompt
    assert "go_to" in prompt
    assert "take_screenshot" in prompt
    assert "ask_user" in prompt
    assert 'fields=[{"name": "username"' in prompt
    assert "2FA" in prompt
    assert "same turn" in prompt
    assert "Do not repeat credentials" in prompt
    assert "Leave the browser open" in prompt


def test_main_prompt_does_not_claim_the_agent_writes_code():
    """main.md is every agent's prompt, including the ones deployed as a
    support bot or a poster. Telling those they are a coding agent puts the
    prompt at war with the skills they were shipped with."""
    prompt = flatten(assemble_prompt(prompts_dir=str(PROMPTS_DIR), tools=[ask_user]))

    lowered = prompt.lower()
    assert "you are a coding agent" not in lowered
    assert "software engineering" not in lowered
    # ...and the coding doctrine went with it
    assert "Avoid Over-Engineering" not in prompt
    assert "ALWAYS read existing files before modifying" not in prompt


def test_role_adds_the_domain_back():
    plain = flatten(assemble_prompt(prompts_dir=str(PROMPTS_DIR), tools=[ask_user]))
    coding = flatten(assemble_prompt(prompts_dir=str(PROMPTS_DIR), tools=[ask_user], role="coding"))

    assert len(coding) > len(plain)
    assert "Avoid Over-Engineering" in coding
    assert "file_path:line_number" in coding
    # Whatever the role, the generic half is always there.
    for prompt in (plain, coding):
        assert "Executing Actions with Care" in prompt
        assert "Delivering Work" in prompt


def test_generic_prompt_covers_irreversible_and_outward_facing_actions():
    """A deployed agent can post publicly, send mail, and deploy. Warning it
    about SQL injection while saying nothing about actions it cannot take back
    is the wrong half of "security" for anything but a coding agent."""
    prompt = flatten(assemble_prompt(prompts_dir=str(PROMPTS_DIR), tools=[ask_user]))

    assert "Executing Actions with Care" in prompt
    assert "confirm" in prompt.lower()
    assert "hard to reverse" in prompt.lower()


def test_being_asked_to_send_is_not_approval_of_the_wording():
    """Caught live on gemini-3.6-flash: "Announce the v2 release to the
    company" was read as authorising the post, so the agent wrote its own
    copy and fired it at #general without showing anyone. Instructing the
    action is not approving the words."""
    prompt = flatten(assemble_prompt(prompts_dir=str(PROMPTS_DIR), tools=[ask_user]))

    assert "Being told to do it is not approval of what you write" in prompt
    assert "show the exact text" in prompt


def test_generic_prompt_requires_reporting_what_actually_happened():
    """Persistence without honesty pushes an agent toward reporting success it
    does not have. The two have to ship together."""
    prompt = flatten(assemble_prompt(prompts_dir=str(PROMPTS_DIR), tools=[ask_user]))

    assert "Report what actually happened" in prompt
    assert "Finish the whole thing" in prompt


def test_unknown_role_fails_loudly():
    """A deployed agent with a typo'd role should die at construction with a
    readable message, not silently serve a prompt missing its domain."""
    with pytest.raises(FileNotFoundError) as excinfo:
        assemble_prompt(prompts_dir=str(PROMPTS_DIR), tools=[ask_user], role="nonexistent")

    assert "Available roles" in str(excinfo.value)
    assert "coding" in str(excinfo.value)
