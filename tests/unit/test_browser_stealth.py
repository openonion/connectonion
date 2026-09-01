"""Unit tests for Onionwright's single driver API health check."""

import importlib.metadata
import importlib.util
import sys
from types import SimpleNamespace

import connectonion.useful_tools.browser_tools.browser as browser_mod

def test_status_ok_when_both_onionwright_apis_are_callable(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "0.0.13.dev5")
    monkeypatch.setitem(
        sys.modules, "onionwright.async_api", SimpleNamespace(async_playwright=lambda: None)
    )
    monkeypatch.setitem(
        sys.modules, "onionwright.sync_api", SimpleNamespace(sync_playwright=lambda: None)
    )

    status, version, detail = browser_mod.driver_stealth_status()

    assert (status, version) == ("ok", "0.0.13.dev5")
    assert "single pinned driver API" in detail


def test_status_broken_when_driver_api_is_incomplete(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "0.0.13.dev5")
    monkeypatch.setitem(
        sys.modules, "onionwright.async_api", SimpleNamespace(async_playwright=None)
    )
    monkeypatch.setitem(
        sys.modules, "onionwright.sync_api", SimpleNamespace(sync_playwright=lambda: None)
    )

    status, version, detail = browser_mod.driver_stealth_status()

    assert (status, version) == ("broken", "0.0.13.dev5")
    assert "install-onion" in detail


def test_status_missing_when_not_installed(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)

    status, version, detail = browser_mod.driver_stealth_status()

    assert status == "missing"
    assert version == ""
    assert "not installed" in detail
