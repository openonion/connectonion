"""A long event or mail-quote title in the calendar must clamp to two lines, not become a wall of wrapped
lines filling the day-grid block. The full text stays on the event's detail panel. Invented notebook.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

LONG = ("Following up on the usage export you promised before the pilot renewal please confirm the September "
        "invoice correction and the revised seat price by Thursday so finance can close the quarter on time")

INJECT = """(long) => {
    const today = agToday();
    REM.calendar = { events: [
        { start: today + "T10:00:00Z", end: today + "T11:30:00Z", title: long },
        { start: today + "T14:00:00Z", end: today + "T15:30:00Z", title: long } ] };
    Object.assign(agendaState || {}, { view: "week", start: "", month: "", sel: "" });
    agendaView();
}"""

MEASURE = """(sel) => [...document.querySelectorAll(sel)].map(el => {
    const line = parseFloat(getComputedStyle(el).lineHeight) || 16;
    return { sw: el.scrollWidth, cw: el.clientWidth, lines: Math.round(el.clientHeight / line),
             text: el.textContent.slice(0, 16) };
})"""


def _page(tmp_path, width):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    from rem_reader_notebook import build
    build(tmp_path / "rem", datetime(2026, 11, 20, tzinfo=timezone.utc))
    html = rem_reader.render(tmp_path / "rem", local=True)
    path = tmp_path / "reader.html"
    path.write_text(html, encoding="utf-8")
    api = sync_playwright().start()
    browser = api.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": width, "height": 1000}, locale="en-US")
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(path.as_uri())
    page.evaluate(INJECT, LONG, isolated_context=False)
    page.wait_for_timeout(250)
    return api, browser, page


def _assert_clamped(page, selector):
    boxes = page.evaluate(MEASURE, selector, isolated_context=False)
    for b in boxes:
        assert b["sw"] <= b["cw"] + 2, f"{selector} overflows horizontally: {b}"
        assert b["lines"] <= 2, f"{selector} is a wall of {b['lines']} lines: {b}"
    return boxes


def test_desktop_grid_event_title_clamps_to_two_lines(tmp_path):
    api, browser, page = _page(tmp_path, 1440)
    try:
        boxes = _assert_clamped(page, ".cal-ev-title")
        assert boxes, "no grid event titles rendered"
    finally:
        browser.close(); api.stop()


def test_phone_daylist_row_title_clamps(tmp_path):
    api, browser, page = _page(tmp_path, 390)
    try:
        # The phone layout lists the day's events as cal-row rows; a long title must clamp there too.
        boxes = page.evaluate(MEASURE, ".cal-row-title", isolated_context=False)
        for b in boxes:
            assert b["sw"] <= b["cw"] + 2, f".cal-row-title overflows: {b}"
            assert b["lines"] <= 2, f".cal-row-title is a wall of {b['lines']} lines: {b}"
    finally:
        browser.close(); api.stop()
