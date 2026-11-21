"""An over-long page's oldest History moves to an archive (2026-11-19): the page's History ends on one linked
line, and the archive opens as a page. A failed run says why in the reader's words, never a Python list.
The notebook is invented. Opt in with CO_REM_BROWSER_TEST=1."""
import os
from urllib.parse import quote

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")
PAGE = "people/avery-lin.md"


@pytest.fixture
def page(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    from connectonion.rem.page_review import archive_history, archive_record
    monkeypatch.setenv("CONNECTONION_REM_CACHE", str(tmp_path / "cache"))
    root = tmp_path / "rem"
    prepare(root)
    book = Notebook(root)
    filler = "and the thread went on with the plan, the dates and who was waiting on what " * 8
    history = "\n".join(f"- 2026-{1 + i // 2:02d}-{10 + i % 2:02d}: Thread {i} ended with a next step, {filler[:600]} [{i + 1}]"
                        for i in range(16))
    relationship = "\n".join(f"- Avery and the user ran part {i} of the pilot, {filler[:600]} [{i + 1}]" for i in range(16))
    text = ("# Avery Lin\n\nAvery runs the Lantern pilot with the user. [1]\n\n## Facts\n- Email: avery@lantern.example [1]\n\n"
            f"## Our relationship\n{relationship}\n\n## History\n{history}\n\n## Sources\n"
            + "\n".join(f"- [{i + 1}] gmail:avery{i:04d} — 2026-01-{10 + i:02d}" for i in range(16))
            + "\n\nInvestigation: mapped 2026-09-01 · investigated 2026-10-01 (gmail)\n")
    text, archive, moved = archive_history(PAGE, text)
    assert moved
    book.write(PAGE, text)
    book.write(archive_record(PAGE), archive)
    html = tmp_path / "reader.html"
    html.write_text(reader.render(root, live=False, local=True), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        tab = browser.new_page(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        tab.route("http*://**/*", lambda route: route.abort())
        tab.goto(html.as_uri() + "#r=" + quote(PAGE))
        tab.locator(".r4-person").wait_for()
        yield tab, len(moved)
        browser.close()


def test_history_ends_on_a_link_that_opens_the_archive_as_a_page(page):
    tab, moved = page
    link = tab.locator("#main a", has_text="archive").first
    link.wait_for(state="attached")
    assert f"{moved} entries moved to" in link.locator("xpath=ancestor::li[1]").inner_text()
    link.scroll_into_view_if_needed()
    link.click()
    tab.wait_for_function("() => decodeURIComponent(location.hash).includes('logs/history/people/avery-lin.md')")
    assert "Avery Lin: earlier history" in tab.locator("#main h1").first.inner_text()
    assert "Thread 0 ended" in tab.locator("#main").inner_text()


def test_a_failed_run_says_why_in_the_readers_words(page):
    tab, _ = page
    tab.evaluate("""() => {
      const r = byPath('people/avery-lin.md'), at = new Date().toISOString();
      r.investigation = { label: 'update', last: '2026-10-01', run: { result: 'failed', reason_kind: 'too_long', started_at: at,
        finished_at: at, reason: 'The page is too long to add to (32,360 characters); the draft is kept and nothing on the page changed.' } };
      KNOWN.clear(); render();
    }""", isolated_context=False)
    line = tab.locator(".person-head .inv-fail")
    assert line.inner_text() == "调查没有完成：页面超过长度上限，候选稿已保存，页面没有改动"
