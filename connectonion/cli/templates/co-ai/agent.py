"""Hosted co-ai coding agent."""

from connectonion import host
from connectonion.cli.co_ai.agent import create_coding_agent

agent = create_coding_agent()
host(agent)
