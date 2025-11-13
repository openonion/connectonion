"""
Useful plugins for ConnectOnion agents.

Pre-built plugins that can be easily imported and used across agents.
"""

from .reflection import reflection
from .react import react
from .image_result_formatter import image_result_formatter

__all__ = ['reflection', 'react', 'image_result_formatter']