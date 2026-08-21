"""`co browser do` bills in the caller, never in the shared daemon (#933).

The daemon used to resolve an API key from its own long-lived environment and
print that account in status. Moving the agent loop to the CLI process removes
both the surprising payer and the reason status needed a billing line.
"""


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
