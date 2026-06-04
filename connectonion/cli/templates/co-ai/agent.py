"""Hosted co-ai coding agent — entrypoint for `co init --template co-ai`.

Mirrors the built-in `co ai` agent (create_coding_agent), wrapped in host() so
`co deploy` can serve it. co_dir points at this project's .co so bundled skills
(.co/skills/) and config (.co/host.yaml) are used, not the global ~/.co.
"""

from pathlib import Path

from connectonion import host
from connectonion.cli.co_ai.agent import create_coding_agent

CO_DIR = Path(__file__).resolve().parent / ".co"


def create_agent():
    return create_coding_agent(browser_channel="chrome", co_dir=CO_DIR)


host(create_agent, co_dir=CO_DIR)
