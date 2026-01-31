"""
Purpose: Event handlers package re-exporting reflect and other lifecycle event handlers
LLM-Note:
  Dependencies: imports from [reflect.py] | imported by [__init__.py main package, user code] | tested via handler tests
  Data flow: re-exports event handler functions/lists
  State/Effects: no state
  Integration: exposes reflect event handler (fires after_tools) | used via Agent(on_events=[reflect])
  Performance: trivial
  Errors: none
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
