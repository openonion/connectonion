"""The full-screen writer dims the page behind it in both themes (#3362, art director): its backdrop, laid over
the page, must be darker than the page. An overlay mixed from ink fogged the page in dark mode, where ink is
near-white. Served like test_rem_reply_compose_browser.py; every /rem/* call is stubbed, nothing is sent."""
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_today_fuse_browser import DRAFT, OVERDUE, today  # noqa: E402,F401

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

READ = """() => { const d = document.querySelector('dialog.writer[open]');
  return [getComputedStyle(d, '::backdrop').backgroundColor, getComputedStyle(document.body).backgroundColor,
          getComputedStyle(document.documentElement).backgroundColor]; }"""


def _rgba(text):
    parts = [float(x) for x in re.findall(r'[\d.]+', text)]
    return parts[:3] + [parts[3] if len(parts) > 3 else 1.0]


def _luminance(rgb):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_writer_backdrop_dims_the_page(today, scheme):
    page, _, _ = today
    page.emulate_media(color_scheme=scheme)
    page.set_viewport_size({"width": 1440, "height": 900})
    page.evaluate(OVERDUE, isolated_context=False)
    page.evaluate(DRAFT, True, isolated_context=False)
    page.evaluate("scrollTo(0, 0)", isolated_context=False)
    page.locator(".qcard.open .mail-write").click()
    page.locator("dialog.writer[open]").wait_for()
    backdrop, body, html = (_rgba(v) for v in page.evaluate(READ, isolated_context=False))
    surface = body if body[3] > 0 else html
    a = backdrop[3]
    assert a > 0, f"{scheme}: the writer has no backdrop colour"
    over = [backdrop[i] * a + surface[i] * (1 - a) for i in range(3)]
    assert _luminance(over) < _luminance(surface), f"{scheme}: backdrop {backdrop} lightens the page {surface}"
