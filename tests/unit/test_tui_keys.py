"""Smoke test for tui.keys module."""

import connectonion.tui.keys as keys


def test_keys_constants():
    assert keys.PASTE_START.startswith("\x1b")
    assert keys.PASTE_END.startswith("\x1b")
