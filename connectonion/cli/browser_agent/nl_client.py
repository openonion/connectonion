"""
Purpose: Run the natural-language browser agent in the CALLER's process, issuing one ordinary daemon request per tool call, so a `do` never holds the single execution lane for its whole run.
LLM-Note:
  Dependencies: imports from [inspect, connectonion Agent, browser_agent.agent (PROMPT_PATH, resolve_api_key), browser_agent.client (run_verb), useful_tools.browser_tools.BrowserAutomation (signatures only, never instantiated)] | imported by [cli/commands/browser_commands.py] | tested by [tests/e2e/cli/test_browser_daemon.py, tests/unit/test_nl_client.py]
  Data flow: run(instruction, tab, headless) → builds an Agent whose tools are generated proxies, one per BrowserAutomation verb → each proxy call formats a shell line and sends it through client.run_verb() as a normal request → the daemon serves it in a few-second slot and replies → the reply string is the tool result the model reads
  State/Effects: holds NO browser and NO page — the daemon owns those | model latency happens here, holding nothing | the caller's own environment pays for the model, so the payer is whoever ran the command
  Integration: exposes run() | replaces daemon._run_nl, which ran the same loop inside one daemon request (#933)
  Performance: one short daemon request per tool call instead of one request per run | the browser is free between the agent's steps, so other sessions interleave
  Errors: a failed verb returns the daemon's own message as the tool result, which is what the model needs to correct itself | authentication is checked once before the loop starts
"""

import inspect

from connectonion import Agent

from .agent import PROMPT_PATH, resolve_api_key
from . import client


# Verbs the agent must never call. `do` would recurse into another agent, and
# the lifecycle verbs belong to the human or the orchestrating skill -- an agent
# that can close the browser can end another session's work mid-task.
_NOT_FOR_THE_AGENT = {
    "do", "close", "close_tab", "closetab", "open_browser", "newtab", "tab",
    "save_state", "tab_status",
}


def _format(verb: str, args: dict) -> str:
    """One shell line for a verb call, quoted so the daemon's shlex sees it whole."""
    import shlex

    parts = [verb]
    for name, value in args.items():
        if value is None:
            continue
        if isinstance(value, bool):
            # The daemon coerces --flag=true/false by the annotation, so send the
            # value rather than bare presence: `--headless` and `--headless=false`
            # must not mean the same thing.
            parts.append(f"--{name}={'true' if value else 'false'}")
        else:
            parts.append(f"--{name}={shlex.quote(str(value))}"
                         if " " in str(value) else f"--{name}={value}")
    return " ".join(parts)


def _make_proxy(verb: str, signature, doc: str, tab, headless: bool):
    """Build one tool that sends `verb` to the daemon and returns its reply.

    The generated function carries the real verb's signature and docstring, so
    the schema the model sees is the same one it saw when these were bound
    methods -- the agent's prompt and habits keep working unchanged.
    """
    params = [p for name, p in signature.parameters.items() if name != "self"]

    def proxy(**kwargs):
        return client.run_verb(_format(verb, kwargs), headless=headless, tab=tab)

    proxy.__name__ = verb
    proxy.__doc__ = doc or f"Run the browser verb {verb}."
    proxy.__signature__ = inspect.Signature(params)
    return proxy


def build_tools(tab, headless: bool):
    """A proxy per public BrowserAutomation verb, each one a daemon request."""
    from connectonion.useful_tools.browser_tools import BrowserAutomation

    tools = []
    for name, member in inspect.getmembers(BrowserAutomation, inspect.isfunction):
        if name.startswith("_") or name in _NOT_FOR_THE_AGENT:
            continue
        tools.append(_make_proxy(name, inspect.signature(member),
                                 inspect.getdoc(member), tab, headless))
    return tools


def run(instruction: str, tab=None, headless: bool = False) -> int:
    """Run the NL agent here, in the caller's process. Returns an exit code.

    The loop, and every model call in it, happens in this process. The daemon
    sees only the individual verbs -- each a short request it can serve between
    other callers' requests. That is the whole fix for #933: the browser is idle
    and available while this agent is thinking, which is most of the time.
    """
    api_key = resolve_api_key()
    if not api_key:
        print("Browser agent requires authentication. Run: co auth")
        return 1

    agent = Agent(
        name="browser_cli",
        model="co/gemini-3.6-flash",
        api_key=api_key,
        system_prompt=PROMPT_PATH,
        tools=build_tools(tab, headless),
        max_iterations=200,
    )
    print(agent.input(instruction))
    return 0
