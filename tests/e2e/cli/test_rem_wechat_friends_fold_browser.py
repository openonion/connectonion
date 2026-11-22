"""WeChat friends with nothing to read yet fold under People instead of filling the table with dashes (opt in).

#3347: every address-book friend gets a page, but WeChat for Mac holds chats for few of them. A page with no
chat and no mail rests (onboard.idle); People shows those friends in one fold, "N WeChat friends with no chats
yet", each opening its page, and keeps the table for people with something to read. Invented notebook.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"


def _rest(root, count):
    """`count` address-book friends with no chats, as onboarding leaves them: mapped pages, resting."""
    from connectonion.rem import onboard
    from connectonion.rem.files import Notebook
    book = Notebook(root)
    rows = []
    for i in range(count):
        record = f"people/friend-{i:04d}-wechat.md"
        book.stub_person(record, f"Friend {i:04d}", [f"wxid_friend{i:04d}"])
        rows.append({"record": record, "rank": 2, "material": False})
    onboard.queue_first(root, "wechat", rows)


@pytest.fixture(params=[1440, 390])
def reader(request, tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = build(tmp_path / "rem", datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    _rest(root, 12)
    errors = []

    def serve(route):
        path = route.request.url[len(BASE) - 1:].split("#")[0]
        if path in ("/", "/index.html"):
            return route.fulfill(body=rem_reader.render(root, local=True), content_type="text/html")
        return route.fulfill(status=200, body=json.dumps({}), content_type="application/json")

    width = request.param
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": width, "height": 900 if width > 500 else 844}, locale="en-US",
                                      reduced_motion="reduce", is_mobile=width < 500, has_touch=width < 500)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        yield page, width
        browser.close()
    assert not errors, errors


def test_resting_friends_fold_out_of_the_people_table(reader):
    page, width = reader
    page.goto(BASE + "#c=people")
    page.wait_for_selector(".people-table")
    table = page.locator(".people-table").inner_text()
    assert "Friend 0000" not in table and "Mara" in table   # the table keeps people with something to read
    fold = page.locator("details.friend-directory")
    assert fold.locator("summary").inner_text() == "12 WeChat friends with no chats yet"
    fold.locator("summary").click()
    links = fold.locator("tbody a")
    assert links.count() == 12 and links.first.inner_text() == "Friend 0000"
    fold.locator("input.directory-find").fill("0011")
    assert fold.locator("tbody a").count() == 1
    fold.locator("tbody a").first.click()
    page.wait_for_function("() => location.hash.includes('friend-0011')")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")


def test_the_fold_reads_in_chinese(reader):
    page, width = reader
    page.goto(BASE + "#c=people")
    page.wait_for_selector(".people-table")
    page.evaluate("() => { setInterfaceLanguage('zh'); }", isolated_context=False)
    page.goto(BASE + "#c=people")
    page.wait_for_selector("details.friend-directory")
    assert page.locator("details.friend-directory summary").inner_text() == "微信好友 · 暂无聊天记录 12 位"
