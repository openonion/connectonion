"""A hash becomes a 提交 chip only when it stands alone in prose; links, URLs, emails and slugs keep their hex (rc36 hunt, #3165).

#3201 taught the reader to turn a short commit hash in prose into a quiet "提交" chip. On the owner's notebook the
same pass also took hex-looking runs out of the middle of things that are not hashes: a profile URL's last segment,
a page slug's hash suffix, a file name, an email's local part. The rc36 hunt found a profile link followed by a
stray "提交" on 18 of 21 sampled pages. A hash is a word of its own; a hex run inside a longer token is part of that
token, and the text of a link is the link's own.
"""

import os
from pathlib import Path

import pytest

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.reader import write_reader

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)

PROFILE = "https://profiles.example/in/wren-hale-5bff1cf880"
PAGE = (
    "# Wren Hale\n\n## Facts\n- Company: [Fernhill](../orgs/fernhill.md)\n"
    f"- LinkedIn: {PROFILE}\n- Email: a1b2c3d4e5@fernhill.example\n\n"
    "## Who they are\nWren runs the venue [1]. Her notes live in pilot-5bff1cf880 and in a1b2c3d4.md; "
    "the board is at https://fernhill.example/r/4f9e2a7c1b3d and www.fernhill.example/b/9c1d2e3f4a. "
    "Her profile is [here](https://profiles.example/in/wren-hale-5bff1cf880). Write to a1b2c3d4e5@fernhill.example. "
    "Fixed in e5f48af0.\n\n"
    "## Sources\n- [1] gmail:18f0aa11bb22cc33dd44ee55 — 2026-07-05\n"
)
INTACT = ["wren-hale-5bff1cf880", "pilot-5bff1cf880", "a1b2c3d4.md", "fernhill.example/r/4f9e2a7c1b3d",
          "fernhill.example/b/9c1d2e3f4a", "a1b2c3d4e5@fernhill.example"]
SHOTS = os.environ.get("REM_PR_SHOTS")


@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize("width", [1440, 390])
def test_only_a_standalone_hash_in_prose_becomes_a_chip(tmp_path, monkeypatch, language, width):
    from patchright.sync_api import sync_playwright

    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/wren-hale.md", PAGE)
    Notebook(root).write("orgs/fernhill.md", "# Fernhill\n\nFernhill hosts pilots.\n")
    path = write_reader(root)
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": width, "height": 900 if width > 400 else 844})
        page.goto(path.as_uri() + "#r=people%2Fwren-hale.md")
        page.evaluate("language => setInterfaceLanguage(language)", language, isolated_context=False)
        page.locator("#main h1").first.wait_for()
        chips = page.evaluate("""() => [...document.querySelectorAll('#main .src-id')].map(c => ({
            title: c.title, inLink: !!c.parentElement.closest('a'), afterLink: c.previousSibling?.nodeType === 1
              && c.previousSibling.matches('a') || /\\S$/.test(c.previousSibling?.nodeValue || ' ') }))""",
                              isolated_context=False)
        # Only the bare hash and the mail id are chips; none sits inside a link or glued to the word before it.
        titles = sorted(c["title"] for c in chips)
        assert "e5f48af0" in titles and set(titles) <= {"e5f48af0", "gmail:18f0aa11bb22cc33dd44ee55"}, chips
        assert not any(c["inLink"] or c["afterLink"] for c in chips), chips
        text = page.locator("#main").inner_text()
        for token in INTACT:
            assert token in text, (token, text[:2000])
        # A link whose text is a URL is never renamed in place.
        links = " ".join(page.evaluate("[...document.querySelectorAll('#main a:not(.src-id)')].map(a => a.textContent)"
                                       ".filter(t => /https?:|www\\.|@/.test(t))", isolated_context=False))
        assert "提交" not in links and "Commit" not in links and "记录" not in links, links
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if SHOTS:
            page.screenshot(path=str(Path(SHOTS) / f"hex-links-{language}-{width}.png"), full_page=True)
        browser.close()
