"""`co browser do` bills in the caller, never in the shared daemon (#933).

The daemon used to resolve an API key from its own long-lived environment and
print that account in status. Moving the agent loop to the CLI process removes
both the surprising payer and the reason status needed a billing line.
"""

import pytest


class _Browser:
    _headless = False
    _tab_meta = {}

    def _context_is_alive(self):
        return True

    def tab_status(self):
        return "Tabs (1):\n  *[main]"


def test_status_has_no_daemon_billing_account(monkeypatch):
    from connectonion.cli.browser_agent import daemon as mod

    instance = mod.BrowserDaemon.__new__(mod.BrowserDaemon)
    instance.browser = _Browser()
    instance.last_command = None
    monkeypatch.setattr(
        mod, "driver_stealth_status", lambda: ("ok", "1.61.2", "stealth patches present")
    )
    monkeypatch.setattr(mod, "installed_browser_path", lambda: "/browser")

    ok, text = instance._status()

    assert ok is True
    assert "Browser: open" in text
    assert "billed to" not in text.lower()
    assert "pays" not in text.lower()


def test_daemon_module_no_longer_imports_or_resolves_model_credentials():
    from connectonion.cli.browser_agent import daemon as mod

    assert not hasattr(mod, "resolve_api_key")
    assert not hasattr(mod, "build_browser_agent")
    assert not hasattr(mod, "_daemon_account")


class _PaidBrowser(_Browser):
    def engine_status(self):
        return {
            "requested_engine": "auto",
            "resolved_engine": "onion",
            "reason": "onion_ready",
            "artifact_id": "chrome/151/linux-x86_64.tar.zst",
            "interval_usd": 0.025,
            "executable": "/runtimes/abc/chrome",
            "paid_session_id": "sess-123",
        }


@pytest.mark.asyncio
async def test_a_paid_session_shows_its_cost_in_status(monkeypatch):
    """Explicit auto may charge, so status names price and live session (#1327)."""
    from connectonion.cli.browser_agent import daemon as mod

    instance = mod.BrowserDaemon.__new__(mod.BrowserDaemon)
    instance.browser = _PaidBrowser()
    instance.last_command = None
    monkeypatch.setattr(
        mod, "driver_stealth_status", lambda: ("ok", "1.61.2", "stealth patches present")
    )

    ok, text = await instance._status_async()

    assert ok is True
    assert "$0.025/interval" in text
    assert "paid session sess-123" in text
