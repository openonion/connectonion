"""Templates drive the browser through the `co browser` CLI, not in-process.

An in-process BrowserAutomation in a template means a second owner of
~/.co/browser_profile alongside the daemon, a Playwright launch at import
time, and ~2.5k tokens of tool schema in every request. These tests pin the
CLI-only wiring so it cannot quietly come back.
"""

from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[2] / "connectonion" / "cli" / "templates"

# hosted-browser is deliberately excluded: it passes tab_idle_ttl and max_tabs
# to BrowserAutomation, and the daemon exposes neither. Converting it would
# silently drop tab reclamation and the concurrent-tab cap, which is the whole
# point of that template.
CLI_BROWSER_TEMPLATES = ["minimal", "browser"]


@pytest.mark.parametrize("template", CLI_BROWSER_TEMPLATES)
def test_template_does_not_wire_an_in_process_browser(template):
    source = (TEMPLATES / template / "agent.py").read_text(encoding="utf-8")

    assert "BrowserAutomation" not in source
    assert "bind_browser_session" not in source


@pytest.mark.parametrize("template", CLI_BROWSER_TEMPLATES)
def test_template_can_still_reach_the_browser(template):
    """Dropping the tool is only safe if the agent keeps a shell to run the CLI."""
    source = (TEMPLATES / template / "agent.py").read_text(encoding="utf-8")

    assert "bash" in source, "no shell tool — the agent cannot run `co browser`"


@pytest.mark.parametrize("template", CLI_BROWSER_TEMPLATES)
def test_template_prompt_teaches_the_cli(template):
    """The verbs move from tool schemas into the prompt; if neither has them,
    the agent has a browser it does not know how to use."""
    prompt_dir = TEMPLATES / template
    prompts = list(prompt_dir.glob("prompt.md")) + list((prompt_dir / "prompts").glob("agent.md"))
    assert prompts, f"{template}: no prompt file found"

    text = "\n".join(p.read_text(encoding="utf-8") for p in prompts)
    assert "co browser" in text
    assert "co browser go_to" in text


def test_browser_template_gates_the_shell_it_gained():
    """Driving the browser by CLI requires bash, which is broader than the
    browser tool it replaced. tool_approval + the default `Bash(co *)`
    whitelist keeps that from being a blank cheque."""
    source = (TEMPLATES / "browser" / "agent.py").read_text(encoding="utf-8")

    assert "tool_approval" in source


def test_prompts_do_not_reference_verbs_the_browser_lacks():
    """`type_text` was named in the browser prompt but never existed on
    BrowserAutomation — the real verbs are type_text_by_selector/keyboard_type."""
    import inspect
    from connectonion.useful_tools.browser_tools import BrowserAutomation

    verbs = {n for n, _ in inspect.getmembers(BrowserAutomation, inspect.isfunction)
             if not n.startswith("_")}
    text = (TEMPLATES / "browser" / "prompts" / "agent.md").read_text(encoding="utf-8")

    assert "type_text(" not in text
    assert "type_text_by_selector" in verbs


@pytest.mark.parametrize("template", CLI_BROWSER_TEMPLATES)
def test_template_prompt_teaches_sharing_the_browser(template):
    """One browser, several agents. A prompt that teaches the verbs but not the
    tab protocol produces agents that navigate over each other's pages — and
    `--needs` is useless if nobody knows to declare it."""
    prompt_dir = TEMPLATES / template
    prompts = list(prompt_dir.glob("prompt.md")) + list((prompt_dir / "prompts").glob("agent.md"))
    text = "\n".join(p.read_text(encoding="utf-8") for p in prompts)

    assert "tab open" in text
    assert "--needs" in text
    assert "tab ls" in text, "an agent must know where to look before touching a tab"
