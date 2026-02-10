"""Tests for browser agent module without Playwright."""

import os

import connectonion.cli.browser_agent.browser as browser_mod


def test_browser_automation_no_playwright(monkeypatch):
    monkeypatch.setattr(browser_mod, "PLAYWRIGHT_AVAILABLE", False)

    browser = browser_mod.BrowserAutomation(use_chrome_profile=False, headless=True)
    msg = browser.open_browser()
    assert "Browser tools not installed" in msg


def test_execute_browser_command_requires_auth(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENONION_API_KEY", raising=False)
    # Ensure no ~/.co/keys.env is picked up
    monkeypatch.setattr(browser_mod.Path, "home", lambda: tmp_path)
    msg = browser_mod.execute_browser_command("take a screenshot")
    assert "requires authentication" in msg
