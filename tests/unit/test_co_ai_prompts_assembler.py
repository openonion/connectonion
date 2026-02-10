"""Tests for prompt assembler utilities."""

from pathlib import Path

from connectonion.cli.co_ai.prompts.assembler import (
    PromptContext,
    interpolate,
    assemble_prompt,
    load_reminder,
    load_agent_prompt,
)


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
    assert "Tool? yes" in out
    assert "Foo tool is foo" in out
    assert "Index" in out
    assert "Example" in out

    reminder = load_reminder(str(prompts), "plan_mode", extra_vars={"PROJECT": "Test"})
    assert reminder.startswith("<system-reminder>")
    assert "Plan for Test" in reminder

    agent_prompt = load_agent_prompt(str(prompts), "explore", extra_vars={"PROJECT": "Test"})
    assert agent_prompt == "Explore Test"
