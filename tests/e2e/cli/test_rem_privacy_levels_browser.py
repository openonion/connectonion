"""Three privacy levels in the reader's top bar (#2840, first slice).

Owner, 2026-11-19: «隐私级别过滤的那么一个按钮，也就跟翻译的按钮应该就在右上角…某些内容默认是蒙版或者默认是消失的…分到一级二级三级».
全部显示 shows every labelled passage; 遮住敏感 (this computer's default) keeps each [sensitive] passage behind a
curtain lifted one at a time; 只看公开 takes [personal] and [sensitive] out of the page. A remote reader starts at 只看公开.
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

SECRET = "Her sister is in hospital this month"
PERSONAL = "Prefers calls before ten"
PAGE = ("# Wren Hale\n\n## Facts\n- Email: wren@example.test [1]\n- Language: English [1]\n\n"
        "## Who they are\nWren runs the venue programme [1]. " + PERSONAL + " [personal] [1]. "
        + SECRET + " [sensitive] [1].\n\n## History\n- 2026-09-30: " + SECRET.lower() + " [sensitive] [1].\n"
        "- 2026-09-28: confirmed the March booking [1].\n\n## Sources\n- [1] file:/notes/wren.md — 2026-09-30\n")
# The reader ties a passage's last word to its source mark, so probes use the words before it.
SECRET_SAYS, PERSONAL_SAYS = "sister is in", "Prefers calls"
SHOTS = Path(os.environ.get("REM_PR_SHOTS", "")) if os.environ.get("REM_PR_SHOTS") else None


def _reader(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/wren-hale.md", PAGE)
    return write_reader(root)


def _open(api, path, width=1440, storage=None):
    browser = api.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": width, "height": 900 if width > 400 else 844}, locale="zh-CN", reduced_motion="reduce")
    page.goto(path.as_uri() + "#r=people%2Fwren-hale.md")
    page.locator("#main h1").first.wait_for()
    return browser, page


def _legible(page, words):
    """Whether any element showing these words paints them in a visible colour."""
    return page.evaluate("""words => [...document.querySelectorAll('#main *')].some(n => [...n.childNodes].some(c =>
      c.nodeType === 3 && c.data.includes(words)) && getComputedStyle(n).color !== 'rgba(0, 0, 0, 0)' && n.getClientRects().length)""",
                         words, isolated_context=False)


def _topmost(page, selector):
    return page.evaluate("""sel => { const n = document.querySelector(sel), b = n.getBoundingClientRect(), points = [];
      for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++)
        points.push([b.left + 16 + (b.width - 32) * i / 4, b.top + 16 + (b.height - 32) * j / 4]);
      return points.filter(([x, y]) => y < innerHeight && x < innerWidth).every(([x, y]) => n.contains(document.elementFromPoint(x, y))); }""",
                         selector, isolated_context=False)


def test_on_this_computer_sensitive_is_covered_by_default_and_lifts_one_at_a_time(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    path = _reader(tmp_path, monkeypatch)
    with sync_playwright() as api:
        browser, page = _open(api, path)
        assert page.evaluate("privacyLevel", isolated_context=False) == "cover"
        assert page.locator("#privacy-level .pl-long").inner_text() == "遮住敏感"
        assert _legible(page, PERSONAL_SAYS)                     # personal is shown at this level
        assert not _legible(page, SECRET_SAYS)                   # every sensitive passage is behind a curtain
        curtains = page.locator("#main .curtain:not(.lifted)")
        assert curtains.count() >= 2
        assert curtains.first.get_attribute("aria-label") == "敏感 · 点一下显示"
        curtains.first.click()
        assert page.locator("#main .curtain.lifted").count() == 1
        assert page.locator("#main .curtain:not(.lifted)").count() == curtains.count()  # the others stay covered
        if SHOTS:
            SHOTS.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(SHOTS / "privacy-cover-1440.png"))
        browser.close()


def test_public_only_takes_labelled_text_out_of_the_page_and_says_how_much(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    path = _reader(tmp_path, monkeypatch)
    with sync_playwright() as api:
        browser, page = _open(api, path)
        page.locator("#privacy-level").click()
        page.get_by_role("menuitemradio", name="只看公开").click()
        page.wait_for_function("privacyLevel === 'public'")
        html = page.evaluate("document.getElementById('main').innerHTML", isolated_context=False)
        assert SECRET_SAYS not in html and PERSONAL_SAYS not in html                       # absent, not hidden
        assert "Wren runs the venue" in html                                                # unlabelled text stays
        assert page.locator("#main .privacy-count").first.inner_text().endswith("处已隐藏")
        if SHOTS:
            page.screenshot(path=str(SHOTS / "privacy-public-1440.png"))
        page.locator("#privacy-level").click()
        page.get_by_role("menuitemradio", name="全部显示").click()
        page.wait_for_function("privacyLevel === 'all'")
        assert _legible(page, SECRET_SAYS) and _legible(page, PERSONAL_SAYS)
        if SHOTS:
            page.screenshot(path=str(SHOTS / "privacy-all-1440.png"))
        browser.close()


def test_the_chosen_level_is_kept_on_this_device_after_a_reload(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    path = _reader(tmp_path, monkeypatch)
    with sync_playwright() as api:
        browser, page = _open(api, path)
        page.evaluate("setPrivacy('all')", isolated_context=False)
        page.wait_for_timeout(300)
        page.reload()
        page.locator("#main h1").first.wait_for()
        page.wait_for_function("privacyLevel === 'all'")
        assert page.locator("#privacy-level .pl-long").inner_text() == "全部显示"
        browser.close()


def test_a_remote_reader_starts_at_public_only(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    path = _reader(tmp_path, monkeypatch)
    html = path.read_text()
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844}, locale="zh-CN")
        # The relay serves the page from another host; nothing there is this computer.
        page.route("https://relay.example/**", lambda route: route.fulfill(body=html, content_type="text/html"))
        page.goto("https://relay.example/rem#r=people%2Fwren-hale.md")
        page.locator("#main h1").first.wait_for()
        assert page.evaluate("privacyLevel", isolated_context=False) == "public"
        assert SECRET_SAYS not in page.evaluate("document.getElementById('main').innerHTML", isolated_context=False)
        browser.close()


def test_the_control_sits_in_the_top_bar_reachable_on_a_phone_and_its_menu_is_on_top(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    path = _reader(tmp_path, monkeypatch)
    with sync_playwright() as api:
        browser, page = _open(api, path, width=390)
        control = page.locator("#privacy-level")
        box = control.bounding_box()
        assert box["height"] >= 44 and box["x"] + box["width"] <= 390
        assert control.evaluate("n => !!n.closest('.top-end')")                      # beside the language toggle
        control.click()
        assert page.get_by_role("menuitemradio").count() == 3
        assert _topmost(page, ".privacy-menu")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if SHOTS:
            page.screenshot(path=str(SHOTS / "privacy-menu-390.png"))
        page.keyboard.press("Escape")
        assert page.locator(".privacy-menu").count() == 0
        if SHOTS:
            page.screenshot(path=str(SHOTS / "privacy-cover-390.png"))
        browser.close()


VISIBLE_TEXT = """() => {
  const seen = [], walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const el = node.parentElement;
    if (!el || !node.data.trim() || el.closest('script, style, [hidden], .curtain:not(.lifted)')) continue;
    const style = getComputedStyle(el);
    if (style.color === 'rgba(0, 0, 0, 0)' || style.visibility === 'hidden' || !el.getClientRects().length) continue;
    seen.push(node.data);
  }
  return seen.join(' ').replace(/\\s+/g, ' ').toLowerCase();
}"""


@pytest.mark.parametrize("width", [1440, 390])
def test_at_the_default_level_no_sensitive_text_is_legible_anywhere(tmp_path, monkeypatch, width):
    """#2840 acceptance: 0 sensitive facts legible at the default. Every visible text node is read, on the record
    (lead, timeline rows, full memory, profile values) and in search results, not only one passage."""
    from patchright.sync_api import sync_playwright
    path = _reader(tmp_path, monkeypatch)
    with sync_playwright() as api:
        browser, page = _open(api, path, width=width)
        page.locator("details.deep-note").evaluate_all("nodes => nodes.forEach(d => d.open = true)")
        assert "hospital" not in page.evaluate(VISIBLE_TEXT, isolated_context=False)
        assert "prefers calls" in page.evaluate(VISIBLE_TEXT, isolated_context=False)  # personal still shows
        page.goto(path.as_uri() + "#q=hospital")
        page.wait_for_timeout(500)
        # The search box and its header echo the query itself; every result row must keep the passage covered.
        rows = page.locator("#main .hits").evaluate_all("lists => lists.map(l => l.innerText).join(' ')").lower()
        shown = page.evaluate(VISIBLE_TEXT, isolated_context=False)
        assert page.locator("#main .hits li").count() >= 1
        assert "hospital this month" not in shown and "in hospital" not in shown, rows
        # Lists draw a page's lead through the same row as tag pages and Today's links.
        page.goto(path.as_uri() + "#c=people")
        page.locator("#main").wait_for()
        page.wait_for_timeout(300)
        assert "in hospital" not in page.evaluate(VISIBLE_TEXT, isolated_context=False)
        browser.close()


def test_a_sensitive_waiting_item_is_covered_in_today_and_the_open_list(tmp_path, monkeypatch):
    """Row-level places draw open items through their own code (Today cards, 等你处理): the default covers them too."""
    from patchright.sync_api import sync_playwright
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/wren-hale.md", PAGE.replace("## History", "## Open threads\n- You owe Wren a note about her sister in hospital [sensitive]; with you since 2026-09-29 [1].\n\n## History"))
    path = write_reader(root)
    with sync_playwright() as api:
        browser, page = _open(api, path)
        for place in ("#", "#view=open"):
            page.goto(path.as_uri() + place)
            page.locator("#main").wait_for()
            page.wait_for_timeout(400)
            assert "in hospital" not in page.evaluate(VISIBLE_TEXT, isolated_context=False), place
        browser.close()
