"""
LLM-Note: Plugin system for OO coding assistant.

This module provides access to specialized plugins that extend the OO agent's
capabilities through the event system.

Key components:
- system_reminder: Plugin for intent detection and contextual guidance injection

Architecture:
- Plugins are event handler bundles that hook into agent lifecycle
- Currently includes system_reminder for adaptive tool guidance
- Plugins export from this module for easy import: from co_ai.plugins import system_reminder
"""

from .system_reminder import system_reminder

__all__ = ['system_reminder']
