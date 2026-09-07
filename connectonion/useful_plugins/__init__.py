"""
Purpose: Export pre-built plugins that extend agent behavior via event hooks
LLM-Note:
  Dependencies: imports from [re_act, image_result_formatter, shell_approval, gmail_plugin, calendar_plugin, ui_stream] | imported by [__init__.py main package] | re-exports plugins for agent consumption
  Data flow: agent imports plugin → passes to Agent(plugins=[plugin]) → plugin event handlers fire on agent lifecycle events
  State/Effects: no state | pure re-exports | plugins modify agent behavior at runtime
  Integration: exposes re_act (ReAct prompting), image_result_formatter (base64 image handling), shell_approval (user confirmation for shell commands), gmail_plugin (Gmail OAuth flow), calendar_plugin (Google Calendar integration), ui_stream (WebSocket event streaming) | plugins are lists of event handlers
  Errors: ImportError if underlying plugin dependencies not installed

Pre-built plugins that can be easily imported and used across agents.
"""

from .auto_compact import auto_compact
from .bind_browser_session import bind_browser_session
from .calendar_plugin import calendar_plugin
from .eval import eval
from .full_access import (
    enable_full_access,
    full_access,
    handle_full_access_mode_change,
)
from .gmail_plugin import gmail_plugin
from .human_jitter import human_jitter
from .image_result_formatter import image_result_formatter
from .no_progress_guard import no_progress_guard
from .prefer_write_tool import prefer_write_tool
from .re_act import re_act
from .runtime_input import RUNTIME_INPUT_FRAME_PREFIX, runtime_input
from .shell_approval import shell_approval
from .skills import skill, skills
from .subagents import subagents, task
from .system_reminder import system_reminder
from .tool_approval import handle_mode_change, tool_approval
from .ui_stream import ui_stream

__all__ = ['re_act', 'eval', 'image_result_formatter', 'shell_approval', 'gmail_plugin', 'calendar_plugin', 'ui_stream', 'system_reminder', 'tool_approval', 'handle_mode_change', 'auto_compact', 'prefer_write_tool', 'full_access', 'enable_full_access', 'handle_full_access_mode_change', 'skills', 'skill', 'subagents', 'task', 'runtime_input', 'RUNTIME_INPUT_FRAME_PREFIX', 'no_progress_guard', 'human_jitter', 'bind_browser_session']
