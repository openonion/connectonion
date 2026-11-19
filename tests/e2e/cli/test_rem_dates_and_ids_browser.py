"""The reader shows dates in the reader's own form, once, and never a raw source id (rc34 hunt, #3165).

Measured on the owner's notebook: 415 ISO dates in page bodies, 33 dates printed twice in a row, 77 raw ids.
The Markdown keeps what was written; only what the reader draws changes.
"""

import os
import re
from pathlib import Path

import pytest

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.reader import write_reader

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)

SESSION = "codex:01a1a594-aaaa-bbbb-cccc-dddddddddddd"
MAIL = "gmail:18f0aa11bb22cc33dd44ee55"
PAGE = (
    "# Wren Hale\n\n## Facts\n- Email: wren@example.test [1]\n- First contact: 2026-07-05 [1]\n\n"
    "## Who they are\n2026-11-07 — Wren runs the venue [1]. Last seen 2026-10-29 (10月29日) at the pilot [2].\n"
    "The plan came from " + SESSION + " and the contract from " + MAIL + ".\n\n"
    "## Our relationship\n- 2026-07-05–17: pilot weeks [1].\n- 2026-07-29–08-04: second round [2].\n"
    "- 2026-08-26–2026-08-28: offsite [2].\n\n"
    "| When | What |\n|---|---|\n| 2026-09-03 | Signed [1] |\n\n"
    "## History\n- 2026-10-01: asked about the renewal [1].\n- 2026-10-02: sent the plan [2].\n\n"
    "## Sources\n- [1] " + MAIL + "\n- [2] " + SESSION + "\n"
)
ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
RAW = re.compile(r"(?:codex|gmail|outlook|claude-code):[\w-]{6,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}|\b[0-9a-f]{24,}\b", re.I)
SHOTS = os.environ.get("REM_PR_SHOTS")


def _visible(page):
    return page.evaluate("""() => { const out = [], walker = document.createTreeWalker(document.getElementById('main'), NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) { const p = n.parentElement;
        if (p.closest('[hidden], details:not([open]) > :not(summary)') || !p.getClientRects().length) continue;
        if (getComputedStyle(p).visibility === 'hidden' || p.closest('.cite')) continue;
        out.push(n.nodeValue); }
      return out.join(' '); }""", isolated_context=False)


@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize("width", [1440, 390])
def test_dates_show_in_the_readers_form_once_and_ids_as_named_chips(tmp_path, monkeypatch, language, width):
    from patchright.sync_api import sync_playwright

    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/wren-hale.md", PAGE)
    path = write_reader(root)
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": width, "height": 900 if width > 400 else 844})
        page.goto(path.as_uri() + "#r=people%2Fwren-hale.md")
        page.evaluate("language => setInterfaceLanguage(language)", language, isolated_context=False)
        page.locator("#main h1").first.wait_for()
        text = _visible(page)
        assert not ISO.findall(text), ISO.findall(text)[:5]
        assert not RAW.findall(text), RAW.findall(text)[:5]
        if language == "zh":
            assert "10月29日 (10月29日)" not in text and "10月29日（10月29日）" not in text
            assert "7月5日–17日" in text and "7月29日–8月4日" in text
        else:
            assert re.search(r"Oct 29\s*\(Oct 29\)", text) is None
        chip = page.locator("#main .src-id").first
        assert chip.count() and chip.get_attribute("title") in (SESSION, MAIL)
        chip.click()
        panel = page.locator("#evidence-panel")
        panel.wait_for(state="visible")
        assert "null" not in panel.inner_text()
        if SHOTS:
            page.screenshot(path=str(Path(SHOTS) / f"dates-{language}-{width}.png"))
        page.keyboard.press("Escape")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        # The Markdown keeps what was written.
        assert "2026-11-07 —" in (root / "people/wren-hale.md").read_text()
        browser.close()
