"""End-to-end guard: the REAL installed Patchright must be the patched stealth driver.

This touches the actual on-disk install (no mocks), so it lives in e2e, not unit. It is the
check that would have caught the silent regression we hit: Patchright's separately-downloaded
driver reverting to the unpatched vanilla Playwright build (navigator.webdriver leaks, the
"controlled by automated test software" infobar). If a future patchright bump lands an
unpatched driver, this fails here instead of shipping a browser with no stealth.
"""

import pytest

from connectonion.useful_tools.browser_tools.browser import driver_stealth_status


def test_real_installed_driver_is_patched():
    status, version, detail = driver_stealth_status()
    if status == "missing":
        pytest.skip("patchright not installed in this environment")
    assert status == "ok", f"installed patchright {version} is not the patched stealth driver: {detail}"
