"""With macOS "reduce motion" on, nothing in the reader animates (#3359 T1). The springs are only curves; the
--t- durations carry the time, and the reduced-motion block zeroes them. Invented notebook."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

PROBE = """() => [...document.querySelectorAll('.widget, .night-card, .menu, .switch')].slice(0, 12).map(el => {
  const s = getComputedStyle(el);
  return [s.animationName, s.animationDuration, s.transitionDuration];
})"""


def _durations(tmp_path, reduced):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    from rem_reader_notebook import build
    build(tmp_path / "rem", datetime(2026, 11, 20, tzinfo=timezone.utc))
    page_file = tmp_path / "reader.html"
    page_file.write_text(rem_reader.render(tmp_path / "rem", local=True), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion=reduced)
        page = context.new_page()
        page.route("http*://**/*", lambda route: route.abort())
        page.goto(page_file.as_uri())
        page.wait_for_selector("#main")
        rows = page.evaluate(PROBE, isolated_context=False)
        browser.close()
    return rows


def _seconds(value):
    return max(float(v.strip().rstrip("s").rstrip("m")) / (1000 if v.strip().endswith("ms") else 1)
               for v in value.split(","))


def test_reduced_motion_zeroes_every_animation(tmp_path):
    rows = _durations(tmp_path, "reduce")
    animated = [r for r in rows if r[0] != "none"]
    assert animated, f"the probe found no animated element: {rows}"
    assert all(_seconds(r[1]) == 0 for r in animated), animated
    assert all(_seconds(r[2]) == 0 for r in rows), rows


def test_without_it_the_rises_still_play(tmp_path):
    rows = _durations(tmp_path, "no-preference")
    assert any(r[0] != "none" and _seconds(r[1]) > 0 for r in rows), rows
