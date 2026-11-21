"""A project page's "N open items are in Today" line opens the Waiting view filtered to that project, with its
items shown — not the reply deck, which holds no card keyed to a project, so the line used to land on an
unrelated card or an empty off-screen panel (#3165). Invented notebook.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


def _reader(tmp_path):
    from connectonion.rem import reader as rem_reader
    from rem_reader_notebook import build
    build(tmp_path / "rem", datetime(2026, 11, 20, tzinfo=timezone.utc))
    html = rem_reader.render(tmp_path / "rem", local=True)
    path = tmp_path / "reader.html"
    path.write_text(html, encoding="utf-8")
    return path


def test_the_project_today_line_opens_the_waiting_view_filtered_to_that_project(tmp_path):
    from patchright.sync_api import sync_playwright
    path = _reader(tmp_path)
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="en-US")
        page.route("http*://**/*", lambda route: route.abort())
        page.goto(path.as_uri() + "#r=projects%2Fharbour.md")
        page.locator("#main").wait_for()
        link = page.locator(".project-today-link").first
        assert link.count() if hasattr(link, "count") else True
        words = link.inner_text()
        assert "in Today" in words, words
        link.click()
        page.wait_for_timeout(400)
        state = page.evaluate("""() => {
          const active = document.querySelector('#main .open-chips .chip.on');
          const items = document.querySelectorAll('#main .today-threads li, #main .qcard, #main .thread, #main .open-list li');
          // topmost: the first item's centre is really the item, not covered by an overlay
          let topmost = true;
          const first = items[0];
          if (first) { const r = first.getBoundingClientRect(); const el = document.elementFromPoint(r.x + r.width/2, r.y + Math.min(12, r.height/2));
            topmost = !!(el && (first.contains(el) || el.contains(first) || first === el)); }
          return { hash: location.hash, active: active ? active.innerText.trim() : null, items: items.length, topmost,
                   onscreen: first ? first.getBoundingClientRect().top < 900 : false };
        }""")
        # Filtered Waiting view, not the deck: the project's own chip is the active filter.
        assert "view=open" in state["hash"], state
        assert "tag=project" in state["hash"], state
        assert state["active"] and "Harbour" in state["active"], state
        # Its items are actually shown, on-screen and topmost — not an empty off-position panel.
        assert state["items"] >= 1, state
        assert state["onscreen"], state
        assert state["topmost"], state
        browser.close()
