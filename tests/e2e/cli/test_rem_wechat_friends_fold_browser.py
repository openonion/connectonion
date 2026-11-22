"""People takes WeChat activity, and WeChat friends with nothing recent fold under the table (opt in).

#3347: every address-book friend gets a page, and a page with nothing to read rests (onboard.idle). #3346: the
night keeps when the owner last talked with each WeChat friend (onboard.activity), so People's last contact, its
90-day count and who wrote last include WeChat, each row says where the person comes from, and 来源 filters by it.
The table keeps people in recent contact: resting friends and friends not talked with in 90 days sit in two
collapsed folds, one line per person. Invented notebook.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
NOW = datetime.now(timezone.utc)


def _friends(root):
    """12 resting friends, one talked with three days ago, one half a year ago: as the night leaves them."""
    from connectonion.rem import onboard
    from connectonion.rem.files import Notebook, state_path, write_json
    book, queued, activity = Notebook(root), [], {}
    for i in range(12):
        record = f"people/friend-{i:04d}-wechat.md"
        book.stub_person(record, f"Friend {i:04d}", [f"wxid_friend{i:04d}"])
        queued.append({"record": record, "rank": 2, "material": False})
    for handle, name, days, mine, n90 in (("wxid_wren", "Wren Pike", 3, False, 14), ("wxid_ash", "Ash Kiln", 180, True, 0)):
        record = f"people/{handle}.md"
        book.stub_person(record, name, [handle])
        queued.append({"record": record, "rank": 0, "material": True})
        activity[handle] = {"last": (NOW - timedelta(days=days)).isoformat(), "mine": mine, "n90": n90, "total": 40}
    onboard.queue_first(root, "wechat", queued)
    write_json(state_path(root, onboard.ACTIVITY), activity)


@pytest.fixture(params=[1440, 390])
def reader(request, tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = build(tmp_path / "rem", datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    _friends(root)
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


def _people(page, hash_="#c=people"):
    page.goto(BASE + hash_)
    page.wait_for_selector(".people-table")


def test_resting_and_quiet_friends_fold_collapsed_under_the_table(reader):
    page, width = reader
    _people(page)
    table = page.locator(".people-table").inner_text()
    assert "Friend 0000" not in table and "Ash Kiln" not in table   # resting and quiet: folded
    assert "Wren Pike" in table and "Mara" in table                  # recent WeChat and mail people: the table
    folds = page.locator("details.friend-directory")
    assert folds.locator("summary").all_inner_texts() == ["WeChat friends · no chats · 12", "WeChat friends · not in 90 days · 1"]
    assert all(d.get_attribute("open") is None for d in folds.all())  # collapsed
    resting = folds.nth(0)
    resting.locator("summary").click()
    lines = resting.locator(".friend-list li")
    assert lines.count() == 12 and lines.first.inner_text() == "Friend 0000"   # one line each; no repeated state
    resting.locator("input.directory-find").fill("0011")
    assert resting.locator(".friend-list li").count() == 1
    resting.locator(".friend-list a").first.click()
    page.wait_for_function("() => location.hash.includes('friend-0011')")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")


def test_wechat_activity_fills_the_columns_and_marks_the_source(reader):
    page, width = reader
    _people(page)
    row = page.locator(".people-table tbody tr", has_text="Wren Pike")
    # Only the rarer source is marked (#3368): with most rows from one source, its mark on every row says nothing.
    # Here WeChat friends outnumber mail people overall (most rest in the folds), so mail is the marked one and
    # a WeChat row carries no mark.
    marks = page.evaluate("() => [...document.querySelectorAll('.people-table tbody tr .src-mark')].map(m => m.textContent)")
    assert set(marks) == {"Mail"}, marks
    assert row.locator(".src-mark").count() == 0
    if width > 500:
        cells = [cell.strip() for cell in row.locator("td").all_inner_texts()]
        assert "14" in cells                                         # 90-day messages from WeChat
        assert "Them" in cells                                       # they wrote last
    names = page.evaluate("() => [...document.querySelectorAll('.people-table tbody tr')].map(tr => tr.innerText)")
    assert next(i for i, text in enumerate(names) if "Wren Pike" in text) < 5   # sorted by when you last talked


def test_the_source_filter_shows_wechat_people_only(reader):
    page, width = reader
    _people(page)
    page.locator(".source-bar a", has_text="WeChat").click()
    page.wait_for_function("() => location.hash.includes('src=wechat')")
    page.wait_for_selector(".people-table")
    table = page.locator(".people-table").inner_text()
    assert "Wren Pike" in table and "Mara" not in table


def test_a_wechat_page_labels_its_id_wechat_and_says_when_you_last_chatted(reader):
    page, width = reader
    page.goto(BASE + "#r=people%2Fwxid_wren.md")
    page.wait_for_selector(".hero-meta")
    assert "WeChat · 14 messages in 90 days" in page.locator(".hero-meta").inner_text()
    labels = page.locator("#main .pc-k, #main .pc-label, #main dt").all_inner_texts()
    assert any("WeChat" in label for label in labels) and not any(label.strip() == "Handle" for label in labels)
    page.goto(BASE + "#r=people%2Ffriend-0001-wechat.md")
    page.wait_for_selector(".hero-meta")
    assert "WeChat friend · no chats yet" in page.locator(".hero-meta").inner_text()


def test_the_folds_read_in_chinese(reader):
    page, width = reader
    _people(page)
    page.evaluate("() => { setInterfaceLanguage('zh'); }", isolated_context=False)
    _people(page)
    assert page.locator("details.friend-directory summary").all_inner_texts() == ["微信好友 · 暂无聊天 12 位", "微信好友 · 近 90 天没聊过 1 位"]
