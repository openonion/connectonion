"""Hosted co-ai coding agent — `co init --template co-ai` entrypoint.

CO_DIR pins skills and host.yaml to this project's .co, not the global ~/.co.
"""

from pathlib import Path

from connectonion import host
from connectonion.cli.co_ai.agent import create_coding_agent

CO_DIR = Path(__file__).resolve().parent / ".co"


def create_agent():
    return create_coding_agent(browser_channel="chrome", co_dir=CO_DIR)


host(create_agent, co_dir=CO_DIR)
