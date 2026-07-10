"""Unit tests for the Patchright stealth-driver integrity check (driver_stealth_status).

Pure/isolated: the driver install is faked with a temp tree and monkeypatch, so these lock
the detection logic (patched vs vanilla vs not-installed) with no dependency on the real
install. The guard that the *real* pinned driver is patched is an e2e test (it touches the
actual install): tests/e2e/cli/test_browser_stealth_e2e.py.
"""

import importlib.util

import connectonion.useful_tools.browser_tools.browser as browser_mod

# The literal switch only the PATCHED driver injects; the vanilla driver never has it.
PATCHED_MARKER = 'browser.launchOptions.args.push("--disable-blink-features=AutomationControlled")'
# A snippet of the VANILLA driver (the exact form we observed on the broken 1.58 install).
VANILLA_SNIPPET = 'assistantMode ? "" : "--enable-automation",'


def _fake_patchright(tmp_path, js_content):
    """Build a fake patchright install tree and return the __file__ to monkeypatch onto it."""
    lib = tmp_path / "patchright" / "driver" / "package" / "lib" / "server" / "chromium"
    lib.mkdir(parents=True)
    (lib / "coreBundle.js").write_text(js_content)
    return str(tmp_path / "patchright" / "__init__.py")


def test_status_ok_when_driver_patched(tmp_path, monkeypatch):
    import patchright
    monkeypatch.setattr(patchright, "__file__", _fake_patchright(tmp_path, PATCHED_MARKER))

    status, version, detail = browser_mod.driver_stealth_status()
    assert status == "ok"
    assert version  # importlib.metadata still reports the installed version
    assert "present" in detail


def test_status_broken_when_driver_vanilla(tmp_path, monkeypatch):
    import patchright
    monkeypatch.setattr(patchright, "__file__", _fake_patchright(tmp_path, VANILLA_SNIPPET))

    status, version, detail = browser_mod.driver_stealth_status()
    assert status == "broken"
    assert "UNPATCHED" in detail
    assert "force-reinstall" in detail  # tells the user how to fix it


def test_status_missing_when_not_installed(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)

    status, version, detail = browser_mod.driver_stealth_status()
    assert status == "missing"
    assert version == ""
    assert "not installed" in detail
