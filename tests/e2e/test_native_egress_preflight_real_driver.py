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
from connectonion.network.proxy_egress import ShareEndpoint, shared_egress_gateway
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


@pytest.mark.slow
def test_real_chromium_resolves_and_egresses_through_the_laptop_proxy():
    if _chrome() is None:
        pytest.skip("no Chrome/Chromium on this machine")
    pytest.importorskip("patchright")

    body, resolved, handled = asyncio.run(_exercise_shared_proxy())

    assert body == "through laptop"
    assert ("example.com", 80) in resolved
    assert handled >= 2  # authenticated DNS plus the numeric tunnel


async def _exercise_shared_proxy():
    from patchright.async_api import async_playwright

    resolved = []

    async def origin(reader, writer):
        try:
            await reader.readuntil(b"\r\n\r\n")
        except asyncio.IncompleteReadError:
            writer.close()
            return
        payload = b"through laptop"
        writer.write(
            b"HTTP/1.1 200 OK\r\nConnection: close\r\n"
            + f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
            + payload
        )
        await writer.drain()
        writer.close()

    origin_server = await asyncio.start_server(origin, "127.0.0.1", 0)
    origin_port = origin_server.sockets[0].getsockname()[1]

    async def laptop_dns(host, port):
        resolved.append((host, port))
        return ("8.8.8.8",)

    async def laptop_dial(_endpoint, _timeout):
        return await asyncio.open_connection("127.0.0.1", origin_port)

    # Stands in for the laptop end of an attached share: a gateway on this
    # machine that resolves and dials with the laptop's own policy.
    share = EgressGateway(
        bind_host="127.0.0.1",
        allow_remote_resolution=True,
        username="connectonion-proxy",
        resolver=laptop_dns,
        dialer=laptop_dial,
    )
    share_endpoint = await share.start()
    gateway = shared_egress_gateway(
        ShareEndpoint(
            share_endpoint.host,
            share_endpoint.port,
            share_endpoint.username,
            share_endpoint.password,
        )
    )
    endpoint = await gateway.start()
    try:
        async with async_playwright() as driver:
            browser = await driver.chromium.launch(
                headless=True,
                executable_path=_chrome(),
                args=list(REMOTE_BROWSER_CHROME_ARGS),
                proxy={
                    "server": f"http://127.0.0.1:{endpoint.port}",
                    "username": endpoint.username,
                    "password": endpoint.password,
                },
            )
            page = await browser.new_page()
            await page.goto("http://example.com/")
            content = await page.text_content("body")
            await browser.close()
    finally:
        await gateway.stop()
        await share.stop()
        origin_server.close()
        await origin_server.wait_closed()
    return content, resolved, share.handled_requests
