"""
Purpose: Export pre-built plugins that extend agent behavior via event hooks
LLM-Note:
  Dependencies: imports from [re_act, image_result_formatter, shell_approval, gmail_plugin, calendar_plugin] | imported by [__init__.py main package] | re-exports plugins for agent consumption
  Data flow: agent imports plugin → passes to Agent(plugins=[plugin]) → plugin event handlers fire on agent lifecycle events
  State/Effects: no state | pure re-exports | plugins modify agent behavior at runtime
  Integration: exposes re_act (ReAct prompting), image_result_formatter (base64 image handling), shell_approval (user confirmation for shell commands), gmail_plugin (Gmail OAuth flow), calendar_plugin (Google Calendar integration) | plugins are lists of event handlers
  Errors: ImportError if underlying plugin dependencies not installed

Pre-built plugins that can be easily imported and used across agents.
"""

from .re_act import re_act
from .eval import eval
from .image_result_formatter import image_result_formatter
from .shell_approval import shell_approval
from .gmail_plugin import gmail_plugin
from .calendar_plugin import calendar_plugin

__all__ = ['re_act', 'eval', 'image_result_formatter', 'shell_approval', 'gmail_plugin', 'calendar_plugin']