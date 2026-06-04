"""Hosted co-ai coding agent — entrypoint for `co init --template co-ai`.

Mirrors the built-in `co ai` agent (create_coding_agent), wrapped in host() so
`co deploy` can serve it. Edit model/max_iterations by passing them to
create_coding_agent().
"""

from connectonion import host
from connectonion.cli.co_ai.agent import create_coding_agent


def create_agent():
    return create_coding_agent(browser_channel="chrome")


host(create_agent)
