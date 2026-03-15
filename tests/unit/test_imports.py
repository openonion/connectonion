"""Import smoke tests to catch package-relative import issues."""
"""
LLM-Note: Tests for imports

What it tests:
- Imports functionality

Components under test:
- Module: imports
"""


import importlib

import pytest


MODULES = [
    "connectonion.cli.browser_agent",
    "connectonion.cli.browser_agent.agent",
    "connectonion.cli.commands.browser_commands",
    "connectonion.cli.commands.copy_commands",
    "connectonion.cli.commands.eval_commands",
    "connectonion.cli.commands.project_cmd_lib",
    "connectonion.useful_prompts.coding_agent.assembler",
]


@pytest.mark.parametrize("module_name", MODULES)
def test_imports_without_errors(module_name: str) -> None:
    """Ensure modules import under package context (no local import leaks)."""
    importlib.import_module(module_name)


@pytest.mark.skip(reason="highlight_screenshot module not implemented yet")
def test_highlight_screenshot_import() -> None:
    """PIL is optional; skip if not installed."""
    pytest.importorskip("PIL")
    importlib.import_module("connectonion.cli.browser_agent.highlight_screenshot")
