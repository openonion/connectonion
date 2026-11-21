"""Every visible date in one local form, printed once, and no raw hex left on a page (rc35 hunt, #3165).

#3194's text pass left gaps the rc35 hunt measured on the owner's notebook: 46 dates printed twice (a prose
"(8月10日)" right before a citation chip that already says 8月10日), timeline rows written "9/3", prose dates
written "8 月 10 日", ISO dates inside links and buttons (a person's company line, source titles), 23 raw hex ids
of 12+ characters and 22 short commit hashes. Code blocks keep what was written.
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
PAGES = {
    "people/wren-hale.md": (
        "# Wren Hale\n\n## Facts\n- Company: [Fernhill](../orgs/fernhill.md) (签名 2026-05-02)\n"
        "- Role: Venue lead (observed 2026-05-02)\n- First contact: 2026-07-05 [1]\n\n"
        "## Who they are\nWren runs the venue (2026-08-10) [2]. 合同在 8 月 10 日签了 [2]。"
        "Fixed in e5f48af0 and 9c1d2e3f4a5b6c7d8e9f [3].\n\n"
        "```\ncommit e5f48af0 on 2026-08-10\n```\n\n"
        "## History\n- 2026-09-03: signed [1].\n- 2026-10-02: sent the plan [2].\n\n"
        "## Sources\n- [1] " + MAIL + " — 2026-07-05\n- [2] " + SESSION + " — 2026-08-10\n- [3] 4f9e2a7c1b3d — 2026-08-11\n"
    ),
    "orgs/fernhill.md": (
        "# Fernhill\n\nFernhill hosted the pilot [1]. Commit a1b2c3d shipped it.\n\n"
        "## Timeline\n- 2026-09-03: pilot [1]\n\n## Sources\n- [1] " + MAIL + " — 2026-08-10\n"
    ),
    "projects/pilot.md": (
        "# Pilot\n\nThe pilot ran 2026-07-05–17 [1]. Commit 0a1b2c3d4e pushed.\n\n"
        "## Sources\n- [1] 9f8e7d6c5b4a39281706 — 2026-07-05\n"
    ),
    "skills/catalog/venue-booking.md": (
        "# Venue booking\n\nBook the venue two weeks ahead (2026-08-10) [1]; the template is in b7c8d9e0f1.\n\n"
        "## Sources\n- [1] " + SESSION + " — 2026-08-10\n"
    ),
}
BAD = {
    "ISO date": re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    "raw hex": re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,}\b", re.I),
    "numeric date": re.compile(r"\b\d{1,2}/\d{1,2}\b"),
    "spaced 月日": re.compile(r"\d+\s+月\s*\d+\s*日|\d+\s*月\s*\d+\s+日"),
}
SHOTS = os.environ.get("REM_PR_SHOTS")


def _visible(page):
    """Each text node the reader shows in #main, outside code blocks; chips count by their label, never their title.

    Checked node by node: a big-number fact draws "7月5" and a smaller "日" as two nodes, which is one date.
    """
    return page.evaluate("""() => { const out = [], walker = document.createTreeWalker(document.getElementById('main'), NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) { const p = n.parentElement;
        if (p.closest('[hidden], pre, code, details:not([open]) > :not(summary)') || !p.getClientRects().length) continue;
        if (getComputedStyle(p).visibility === 'hidden') continue;
        out.push(n.nodeValue); }
      return out; }""", isolated_context=False)


def _open(page, path, record, language):
    page.goto(path.as_uri() + "#r=" + record.replace("/", "%2F"))
    page.evaluate("language => setInterfaceLanguage(language)", language, isolated_context=False)
    page.locator("#main h1").first.wait_for()
    page.evaluate("document.querySelectorAll('#main details').forEach(d => d.open = true)", isolated_context=False)


@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize("width", [1440, 390])
def test_every_visible_date_is_local_and_once_and_no_raw_hex_is_left(tmp_path, monkeypatch, language, width):
    from patchright.sync_api import sync_playwright

    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = tmp_path / "rem"
    prepare(root)
    for record, text in PAGES.items():
        Notebook(root).write(record, text)
    path = write_reader(root)
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": width, "height": 900 if width > 400 else 844})
        for record in PAGES:
            _open(page, path, record, language)
            nodes = _visible(page)
            for name, pattern in BAD.items():
                found = [hit for node in nodes for hit in pattern.findall(node)]
                assert not found, (record, name, found[:5])
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), record
        _open(page, path, "people/wren-hale.md", language)
        text = " ".join(_visible(page))
        # The chip after "the venue" already says Aug 10; the prose copy goes.
        assert not re.search(r"venue\s*[（(]", text), text
        assert "合同在 8月10日签" in text
        # A short commit hash is a named chip; hovering shows the whole hash.
        commit = page.locator("#main .src-id[title='e5f48af0']")
        assert commit.count() == 1 and commit.inner_text().strip() in ("提交", "Commit")
        # A source whose title is a hex id reads as its kind and date.
        titles = " ".join(page.locator("#main .src-row").all_inner_texts())
        assert not BAD["raw hex"].search(titles) and re.search(r"8月11日|Aug 11|11 Aug", titles), titles
        # Code blocks keep what was written.
        assert "commit e5f48af0 on 2026-08-10" in page.locator("#main pre").first.inner_text()
        if SHOTS:
            page.screenshot(path=str(Path(SHOTS) / f"dates-hex-{language}-{width}.png"), full_page=True)
        browser.close()
