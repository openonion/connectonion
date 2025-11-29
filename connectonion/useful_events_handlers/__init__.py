"""
Useful event handlers for ConnectOnion agents.

Event handlers fire at specific points in the agent lifecycle.
Use on_events parameter to register them with your agent.

Usage:
    from connectonion import Agent
    from connectonion.useful_events_handlers import reflect

    agent = Agent("assistant", on_events=[reflect])
"""

from .reflect import reflect

__all__ = ['reflect']
