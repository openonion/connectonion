"""
Useful plugins for ConnectOnion agents.

Pre-built plugins that can be easily imported and used across agents.
"""

from .reflection import reflection
from .react import react
from .image_result_formatter import image_result_formatter
from .shell_approval import shell_approval

__all__ = ['reflection', 'react', 'image_result_formatter', 'shell_approval']