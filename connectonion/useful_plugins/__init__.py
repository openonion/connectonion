"""
Useful plugins for ConnectOnion agents.

Pre-built plugins that can be easily imported and used across agents.
"""

from .re_act import re_act
from .image_result_formatter import image_result_formatter
from .shell_approval import shell_approval
from .gmail_plugin import gmail_plugin
from .calendar_plugin import calendar_plugin

__all__ = ['re_act', 'image_result_formatter', 'shell_approval', 'gmail_plugin', 'calendar_plugin']