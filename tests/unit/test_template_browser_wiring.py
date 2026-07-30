"""The agent drives the browser through the `co browser` CLI, not in-process.

An in-process BrowserAutomation means a second owner of ~/.co/browser_profile
alongside the daemon, a Playwright launch at import time, and ~2.5k tokens of
tool schema in every request. These tests pin the CLI-only wiring so it cannot
quietly come back.

There is one template now (co-ai), and it is the same agent as `co ai`, so the
browser knowledge lives in the shared prompt rather than per-template prompt
files. That makes these properties the SDK's to keep, not each template's.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "connectonion"
TEMPLATE = ROOT / "cli" / "templates" / "co-ai"
BROWSER_PROMPT = ROOT / "cli" / "co_ai" / "prompts" / "browser.md"


def test_template_does_not_wire_an_in_process_browser():
    source = (TEMPLATE / "agent.py").read_text(encoding="utf-8")

    assert "BrowserAutomation" not in source
    assert "bind_browser_session" not in source


def test_agent_can_still_reach_the_browser():
    """Dropping the tool is only safe if the agent keeps a shell to run the CLI."""
    source = (ROOT / "cli" / "co_ai" / "agent.py").read_text(encoding="utf-8")

    assert "bash" in source, "no shell tool — the agent cannot run `co browser`"


def test_prompt_teaches_the_cli():
    """The verbs move from tool schemas into the prompt; if neither has them,
    the agent has a browser it does not know how to use."""
    text = BROWSER_PROMPT.read_text(encoding="utf-8")

    assert "co browser" in text
    assert "co browser go_to" in text


def test_shell_the_agent_gained_is_gated():
    """Driving the browser by CLI requires bash, which is broader than the
    browser tool it replaced. tool_approval + the default `Bash(co *)`
    whitelist keeps that from being a blank cheque."""
    source = (ROOT / "cli" / "co_ai" / "agent.py").read_text(encoding="utf-8")

    assert "tool_approval" in source


def test_prompts_do_not_reference_verbs_the_browser_lacks():
    """`type_text` was named in the browser prompt but never existed on
    BrowserAutomation — the real verbs are type_text_by_selector/keyboard_type."""
    import inspect
    from connectonion.useful_tools.browser_tools import BrowserAutomation

    verbs = {n for n, _ in inspect.getmembers(BrowserAutomation, inspect.isfunction)
             if not n.startswith("_")}
    text = BROWSER_PROMPT.read_text(encoding="utf-8")

    assert "type_text(" not in text
    assert "type_text_by_selector" in verbs


def test_prompt_teaches_sharing_the_browser():
    """One browser, several agents. A prompt that teaches the verbs but not the
    tab protocol produces agents that navigate over each other's pages — and
    `--needs` is useless if nobody knows to declare it."""
    text = BROWSER_PROMPT.read_text(encoding="utf-8")

    assert "tab open" in text
    assert "--needs" in text
    assert "tab ls" in text, "an agent must know where to look before touching a tab"
