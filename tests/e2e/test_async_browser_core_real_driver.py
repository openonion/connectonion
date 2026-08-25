"""Real-driver acceptance for the internal 1.8 async browser core.

Run explicitly while #498 is in progress:

    python -m pytest tests/e2e/test_async_browser_core_real_driver.py -m slow -q

The ordinary matrix deselects slow tests; the 1.8 exact-artifact gate will run
this against an installed wheel and browser before an alpha is promoted.
"""

import asyncio
import gc
import json

import pytest

from connectonion.useful_tools.browser_tools._async_browser import (
    ASYNC_BROWSER_AVAILABLE,
    AsyncBrowserCore,
)


@pytest.mark.slow
def test_real_async_driver_keeps_sessions_isolated_and_interleaves(tmp_path, monkeypatch):
    asyncio.run(_exercise_real_async_driver(tmp_path, monkeypatch))


async def _exercise_real_async_driver(tmp_path, monkeypatch):
    if not ASYNC_BROWSER_AVAILABLE:
        pytest.skip("patchright async API is not installed")

    monkeypatch.setenv("CO_BROWSER_PROFILE_DIR", str(tmp_path / "profile"))
    browser = AsyncBrowserCore(headless=True, use_mock_keychain=True)
    loop = asyncio.get_running_loop()
    loop_errors = []
    timings = {"started": loop.time()}
    close_result = None
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: loop_errors.append(context))

    try:
        await browser.open_browser()
        timings["opened"] = loop.time()
        try:
            pages = {}
            for session, marker in (("A", "alpha"), ("B", "beta")):
                browser._bind_session(session)
                await browser.go_to(
                    f"data:text/html,<title>{marker}</title><p>{marker}</p>"
                    f"<input id=editor value={marker}>",
                    purpose="async core acceptance",
                    who=session,
                )
                pages[session] = browser.page

            async def hold_tab_a():
                browser._bind_session("A")
                return await browser.wait(2)

            async def read_tab_b():
                browser._bind_session("B")
                return await browser.get_text()

            held = asyncio.create_task(hold_tab_a())
            await asyncio.sleep(0.05)
            text_b = await asyncio.wait_for(read_tab_b(), timeout=0.5)

            assert "beta" in text_b
            assert held.done() is False
            assert await held == "Waited 2 seconds"
            timings["interleaved"] = loop.time()
            assert pages["A"] is not pages["B"]

            browser._bind_session("A")
            await browser.page.locator("#editor").focus()
            focused = json.loads(await browser.get_focused_element())
            assert focused["is_editable"] is True
            assert focused["value_preview"] == "alpha"
        finally:
            browser._bind_session(None)
            close_result = await browser.close()
            timings["closed"] = loop.time()
            gc.collect()
            await asyncio.sleep(0.1)
    finally:
        loop.set_exception_handler(previous_handler)

    assert close_result == "Browser closed. Session saved for next time."
    assert not loop_errors, {"timings": timings, "errors": [
        {
            "message": error.get("message"),
            "exception": repr(error.get("exception")),
            "origin": [
                f"{frame.name}:{frame.lineno}"
                for frame in (getattr(error.get("future"), "_source_traceback", None) or [])
                if "patchright" in frame.filename
            ][-4:],
        }
        for error in loop_errors
    ]}
