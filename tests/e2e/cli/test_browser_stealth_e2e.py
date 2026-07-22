"""End-to-end stealth guards for the real browser stack (no mocks).

Two layers:
  1. driver integrity — the installed Patchright must still be the patched stealth build.
  2. humanized input (issue #222) — driving the REAL BrowserAutomation tool methods
     (go_to / mouse_click / keyboard_type, the same verbs `co browser` calls) must emit
     human-shaped events and pass the environment fingerprint checkers.

The layer-2 tests need a real headful browser, so they run only when a display is present
(locally: `xvfb-run -a python -m pytest tests/e2e/cli/test_browser_stealth_e2e.py`). They
skip cleanly in a plain CI shell with no DISPLAY.
"""

import os
import statistics
import urllib.parse

import pytest

from connectonion.useful_tools.browser_tools.browser import (
    BROWSER_AVAILABLE,
    BrowserAutomation,
    driver_stealth_status,
)


def test_real_installed_driver_is_patched():
    status, version, detail = driver_stealth_status()
    if status == "missing":
        pytest.skip("patchright not installed in this environment")
    assert status == "ok", f"installed patchright {version} is not the patched stealth driver: {detail}"


# ---------------------------------------------------------------------------
# Humanized-input e2e — drives the real tool methods through a real browser.
# ---------------------------------------------------------------------------

# A page that records the input events a behavioral detector would score, into the shared
# DOM (Patchright evaluates in an isolated world, so page-script globals aren't readable —
# dataset on a DOM node is).
RECORDER_PAGE = (
    "<!doctype html><meta charset=utf-8>"
    "<input id=box style='position:absolute;left:60px;top:80px;width:220px;height:32px'>"
    "<button id=btn style='position:absolute;left:60px;top:140px;width:120px;height:36px'>go</button>"
    "<b id=rec></b>"
    "<script>"
    "const r=document.getElementById('rec');"
    "addEventListener('mousemove',()=>{r.dataset.moves=(+r.dataset.moves||0)+1});"
    "addEventListener('mousedown',e=>{r.dataset.down=e.timeStamp});"
    "addEventListener('mouseup',e=>{r.dataset.up=e.timeStamp});"
    "document.getElementById('box').addEventListener('keydown',"
    "e=>{r.dataset.keys=(r.dataset.keys?r.dataset.keys+',':'')+e.timeStamp});"
    "</script>"
)


@pytest.fixture
def browser():
    if not BROWSER_AVAILABLE:
        pytest.skip("patchright not installed")
    if not os.environ.get("DISPLAY"):
        pytest.skip("no DISPLAY — headful stealth browser needs a display (run under xvfb-run)")
    b = BrowserAutomation(headless=False)
    b.open_browser()
    if not b.page:
        pytest.skip("browser failed to launch in this environment")
    yield b
    b.close()


def _eval(browser, js):
    """Evaluate JS on the browser worker thread (the page is thread-bound)."""
    return browser._executor.submit(lambda: browser.page.evaluate(js)).result()


def test_humanized_input_event_shape_end_to_end(browser):
    """mouse_click + keyboard_type — the real co-browser verbs — must produce a curved
    multi-step move, a non-zero press dwell, and variable keystroke timing."""
    data_url = "data:text/html," + urllib.parse.quote(RECORDER_PAGE)
    browser.go_to(data_url, purpose="stealth event-shape test", who="e2e")

    browser.mouse_click(160, 96)              # focus the input (center of #box)
    browser.keyboard_type("hello human typing")

    data = _eval(browser, "() => ({...document.getElementById('rec').dataset})")
    moves = int(data.get("moves", 0))
    dwell = float(data.get("up", 0)) - float(data.get("down", 0))
    key_times = [float(t) for t in data.get("keys", "").split(",") if t]
    gaps = [b - a for a, b in zip(key_times, key_times[1:])]
    jitter = statistics.pstdev(gaps) if len(gaps) > 1 else 0

    assert moves >= 8, f"expected a curved multi-step move, got {moves} mousemove events"
    assert dwell > 10, f"expected a human mousedown->up dwell, got {dwell:.0f}ms"
    assert len(key_times) >= len("hello human typing") - 2, "expected per-character keystrokes"
    assert jitter > 5, f"expected variable keystroke timing, stdev was {jitter:.0f}ms"


def test_environment_checkers_pass_end_to_end(browser):
    """The real browser must clear the environment fingerprint tells on a live page."""
    browser.go_to("https://bot.sannysoft.com/", purpose="stealth fingerprint test", who="e2e")
    tells = _eval(browser, """() => ({
        webdriver: navigator.webdriver,
        headlessUA: /Headless/i.test(navigator.userAgent),
        chrome: typeof window.chrome === 'object',
        plugins: navigator.plugins.length,
        languages: (navigator.languages || []).length,
    })""")

    assert not tells["webdriver"], "navigator.webdriver leaked"
    assert not tells["headlessUA"], "userAgent advertises Headless"
    assert tells["chrome"], "window.chrome missing"
    assert tells["plugins"] > 0, "no navigator.plugins"
    assert tells["languages"] > 0, "no navigator.languages"
