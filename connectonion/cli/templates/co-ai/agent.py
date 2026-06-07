"""Hosted co-ai coding agent."""

from pathlib import Path

from connectonion import host
from connectonion.cli.co_ai.agent import create_coding_agent

CO_DIR = Path(__file__).resolve().parent / ".co"

agent = create_coding_agent()
host(agent, co_dir=CO_DIR)
