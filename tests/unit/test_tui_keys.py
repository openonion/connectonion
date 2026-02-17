"""Smoke test for tui.keys module."""
"""
LLM-Note: Tests for tui keys

What it tests:
- Tui Keys functionality

Components under test:
- Module: tui_keys
"""


import connectonion.tui.keys as keys


def test_keys_constants():
    assert keys.PASTE_START.startswith("\x1b")
    assert keys.PASTE_END.startswith("\x1b")
