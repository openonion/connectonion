"""One compact cluster in the top bar (rc34 check, Mac session): the bar had grown to four controls,
"369 页还没有中文版 · 翻译 · 遮住敏感 · EN", and truncated on a phone. Now: the language toggle with the untranslated
count as a small badge (progress and Translate in its menu) and the privacy level as a short word; on a phone both
live in one 显示 menu, nothing truncated."""

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
SHOTS = Path(os.environ["REM_PR_SHOTS"]) if os.environ.get("REM_PR_SHOTS") else None


def _reader(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = tmp_path / "rem"
    prepare(root)
    book = Notebook(root)
    for n in range(12):
        book.write(f"people/p{n}.md", f"# Person {n}\n\n## Who they are\nRuns the venue programme number {n} [1].\n\n## Sources\n- [1] file:/notes/p{n}.md\n")
    return write_reader(root)


def _open(api, path, width):
    browser = api.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": width, "height": 900 if width > 400 else 844}, is_mobile=width < 400, has_touch=width < 400)
    page.goto(path.as_uri())
    page.evaluate("() => { setInterfaceLanguage('zh'); }", isolated_context=False)
    page.wait_for_timeout(300)
    return browser, page


def _topmost(page, selector):
    return page.evaluate("""sel => { const n = document.querySelector(sel), b = n.getBoundingClientRect(), pts = [];
      for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) pts.push([b.left + 16 + (b.width - 32) * i / 4, b.top + 16 + (b.height - 32) * j / 4]);
      return pts.filter(([x, y]) => y < innerHeight && x < innerWidth).every(([x, y]) => n.contains(document.elementFromPoint(x, y))); }""",
                         selector, isolated_context=False)


def test_desktop_top_bar_is_a_badge_on_the_language_toggle_and_a_short_privacy_word(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    path = _reader(tmp_path, monkeypatch)
    with sync_playwright() as api:
        browser, page = _open(api, path, 1440)
        bar = page.locator(".top-end")
        text = bar.inner_text()
        assert "还没有中文版" not in text and "翻译" not in text  # the long line moved into the menu
        badge = page.locator("#lang-progress .lang-badge")
        assert badge.is_visible() and badge.inner_text().strip().isdigit()
        assert page.locator("#privacy-level").inner_text().strip() in ("公开", "遮敏感", "全部")
        badge.click()
        menu = page.locator(".lang-menu")
        menu.wait_for()
        assert "页还没有中文版" in menu.inner_text()
        assert _topmost(page, ".lang-menu")
        if SHOTS:
            page.screenshot(path=str(SHOTS / "topbar-1440.png"))
        page.keyboard.press("Escape")
        assert page.locator(".lang-menu").count() == 0
        browser.close()


def test_phone_top_bar_is_one_display_menu_with_language_translation_and_privacy(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    path = _reader(tmp_path, monkeypatch)
    with sync_playwright() as api:
        browser, page = _open(api, path, 390)
        for hidden in ("#lang-toggle", "#lang-progress", ".privacy-level-host"):
            assert not page.locator(hidden).is_visible(), hidden
        show = page.locator("#display-menu")
        assert show.is_visible() and show.inner_text().strip() == "显示"
        box = show.bounding_box()
        assert box["height"] >= 44 and box["width"] >= 44
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        show.click()
        pop = page.locator(".display-pop")
        pop.wait_for()
        text = pop.inner_text()
        assert "English" in text and "中文" in text and "页还没有中文版" in text
        assert "全部显示" in text and "遮住敏感" in text and "只看公开" in text
        assert _topmost(page, ".display-pop")
        assert page.evaluate("[...document.querySelectorAll('.display-pop *')].every(n => n.scrollWidth <= n.clientWidth + 1 || getComputedStyle(n).overflow === 'visible')")
        if SHOTS:
            page.screenshot(path=str(SHOTS / "topbar-display-390.png"))
        pop.get_by_role("menuitemradio", name="只看公开").click()
        assert page.evaluate("privacyLevel", isolated_context=False) == "public"
        assert page.locator(".display-pop").count() == 0
        browser.close()
