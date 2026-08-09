"""Your ConnectOnion agent — the same agent as `co ai`, wrapped in host().

This is the whole agent. You don't add tools here to make it useful; it already
has files, shell, browser, todos, and sub-agents. What makes it
*yours* is what sits next to it:

    .co/skills/<name>/SKILL.md   the procedures it should follow
    role=...                     what kind of agent it is

Run it:
    python agent.py     serve over HTTP/WS + relay
    co deploy           ship it

Roles ship with the SDK in connectonion/cli/co_ai/prompts/roles/. Pass
role=None for an agent with no domain at all. Everything else — how it plans,
asks, reports, and handles irreversible actions — comes from the shared prompt,
so it improves when the SDK does.
"""

from connectonion import host
from connectonion.cli.co_ai.agent import create_agent

agent = create_agent(role="coding")

host(agent)
