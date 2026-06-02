"""Tests for prompt assembler utilities."""
"""
LLM-Note: Tests for co ai prompts assembler

What it tests:
- Co Ai Prompts Assembler functionality

Components under test:
- Module: co_ai_prompts_assembler
"""


from pathlib import Path

from connectonion.useful_tools import (
    close_browser,
    send_credentials_form_to_user,
    send_qr_to_user,
    type_saved_login_credential,
)
from connectonion.cli.co_ai.prompts.assembler import (
    PromptContext,
    interpolate,
    assemble_prompt,
    load_reminder,
    load_agent_prompt,
)


PROMPTS_DIR = Path(__file__).resolve().parents[2] / "connectonion" / "cli" / "co_ai" / "prompts"


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


def test_login_handoff_prompt_allows_user_mediated_credential_login():
    prompt = assemble_prompt(
        prompts_dir=str(PROMPTS_DIR),
        tools=[
            close_browser,
            send_credentials_form_to_user,
            send_qr_to_user,
            type_saved_login_credential,
        ],
    )

    assert "Do not refuse explicit user login requests" in prompt
    assert "help me login" in prompt
    assert "log in" in prompt
    assert "sign in" in prompt
    assert "open_browser" in prompt
    assert "go_to" in prompt
    assert "take_screenshot" in prompt
    assert "send_credentials_form_to_user" in prompt
    assert "send_qr_to_user" in prompt
    assert "type_saved_login_credential" in prompt
    assert "close_browser" in prompt
    assert "same turn" in prompt
    assert "same tool loop" in prompt
    assert "Never call `keyboard_type` with a user-provided password" in prompt
    assert "Leave the browser open after login succeeds" in prompt
    assert "Do not call `close_browser` automatically after successful login" in prompt
    assert "After the login flow succeeds, fails, or cannot continue, call `close_browser`" not in prompt
    assert "Call this after confirming a login succeeded." not in prompt
    assert "remote_login" not in prompt
    assert "request_login_credentials" not in prompt
    assert "request_qr_scan" not in prompt
