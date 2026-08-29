"""Real-driver acceptance for the native egress preflight.

Run explicitly (the ordinary matrix deselects slow tests):

    python -m pytest tests/e2e/test_native_egress_preflight_real_driver.py -m slow -q

Everything else that exercises this preflight uses a fake page, and a fake page
is where its two blocking defects hid: it returned a response object where real
Chromium raises, and it hard-coded a status the real gateway never sends. The
preflight was green in every test and could not pass once, against anything.

So this file drives the real thing in both directions. Passing on a correct
launch is half the proof; the other half is that a genuine leak still fails.
"""

import asyncio
import shutil
from pathlib import Path

import pytest

from connectonion.network.host.egress_gateway import EgressGateway
from connectonion.network.host.private_browser_runtime import (
    REMOTE_BROWSER_CHROME_ARGS,
)
from connectonion.useful_tools.browser_tools.native_egress import (
    NativeEgressPreflightError,
    run_native_egress_preflight,
)

_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)


def _chrome() -> str | None:
    for candidate in _CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return shutil.which("google-chrome") or shutil.which("chromium")


async def _run_preflight(args: tuple[str, ...]) -> tuple[bool, int]:
    """Launch real Chromium behind a real gateway; report (passed, requests)."""
    from patchright.async_api import async_playwright

    gateway = EgressGateway()
    endpoint = await gateway.start()
    try:
        async with async_playwright() as driver:
            browser = await driver.chromium.launch(
                headless=True,
                executable_path=_chrome(),
                args=list(args),
                proxy={
                    "server": f"http://127.0.0.1:{endpoint.port}",
                    "username": endpoint.username,
                    "password": endpoint.password,
                },
            )
            context = await browser.new_context()
            try:
                await run_native_egress_preflight(
                    "remote-egress-v1", context, gateway=gateway
                )
                passed = True
            except NativeEgressPreflightError:
                passed = False
            await context.close()
            await browser.close()
    finally:
        await gateway.stop()
    return passed, gateway.handled_requests


@pytest.mark.slow
def test_the_preflight_passes_against_a_real_gateway_and_real_chromium():
    if _chrome() is None:
        pytest.skip("no Chrome/Chromium on this machine")
    pytest.importorskip("patchright")

    args = tuple(
        arg for arg in REMOTE_BROWSER_CHROME_ARGS if not arg.startswith("--user-data-dir")
    )
    passed, handled = asyncio.run(_run_preflight(args))

    assert passed, "the preflight cannot pass against the real stack"
    # Every probe reached the gateway rather than silently doing nothing.
    assert handled >= 6, handled


@pytest.mark.slow
def test_a_real_loopback_leak_still_fails_the_preflight():
    """The other direction: without this, passing proves only that it is lenient."""
    if _chrome() is None:
        pytest.skip("no Chrome/Chromium on this machine")
    pytest.importorskip("patchright")

    # `<-loopback>` subtracts Chromium's implicit localhost bypass. Putting the
    # address back restores a real direct path to the sentinel.
    leaking = tuple(
        "--proxy-bypass-list=127.0.0.1"
        if arg == "--proxy-bypass-list=<-loopback>"
        else arg
        for arg in REMOTE_BROWSER_CHROME_ARGS
        if not arg.startswith("--user-data-dir")
    )
    passed, _ = asyncio.run(_run_preflight(leaking))

    assert not passed, "a genuine loopback leak passed the preflight"
