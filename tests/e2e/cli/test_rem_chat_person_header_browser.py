"""A chat-only person page says what the chats already tell, before any investigation (#3372; opt in).

On the owner's notebook a WeChat person page not yet investigated showed a raw wxid as its main fact and nothing
about the conversation ("一串 wxid_ 开头的乱码要来干嘛？上次聊了什么一个字都没有"). The header now gives the last
exchange (when, who wrote last), the 90-day count and the earliest chat, and the last message as one line that is
[sensitive]: covered at this computer's default level, readable at Show all. The id moves to ⋯ → Copy WeChat ID.
Invented notebook.
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
PREVIEW = "See you at the harbour on Friday"


def _wren(root):
    from connectonion.rem import onboard
    from connectonion.rem.files import Notebook, state_path, write_json
    Notebook(root).stub_person("people/wren-pike.md", "Wren Pike", ["wxid_wrenpike99"])
    write_json(state_path(root, onboard.ACTIVITY), {"wxid_wrenpike99": {
        "last": (NOW - timedelta(days=1)).isoformat(), "mine": False, "n90": 12, "total": 40,
        "first": "2024-03-05T09:00:00+00:00", "preview": PREVIEW}})


@pytest.fixture(params=[1440, 390])
def reader(request, tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = build(tmp_path / "rem", datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    _wren(root)
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
        page.goto(BASE + "#r=people%2Fwren-pike.md")
        page.wait_for_selector(".r4-name")
        yield page, width
        browser.close()
    assert not errors, errors


def test_the_header_says_the_last_exchange_the_count_and_since_when(reader):
    page, _ = reader
    meta = page.locator(".hero-meta").inner_text()
    assert "12 messages in 90 days" in meta and "they said last" in meta and "chatting since" in meta and "2024" in meta


def test_the_last_message_is_covered_by_default_and_readable_at_show_all(reader):
    page, _ = reader
    # This computer's default level is "cover" (rem.test counts as elsewhere, so set it as the Mac would).
    page.evaluate("() => setPrivacy('cover')", isolated_context=False)
    page.wait_for_timeout(200)
    curtain = page.locator(".hero-preview .curtain:not(.lifted)")
    assert curtain.count() == 1
    assert curtain.evaluate("node => getComputedStyle(node).color") in ("rgba(0, 0, 0, 0)", "transparent")
    page.evaluate("() => setPrivacy('all')", isolated_context=False)
    page.wait_for_timeout(200)
    assert PREVIEW in page.locator(".hero-preview").inner_text()
    page.evaluate("() => setPrivacy('public')", isolated_context=False)
    page.wait_for_timeout(200)
    assert page.locator(".hero-preview").count() == 0 or not page.locator(".hero-preview").first.is_visible()


def test_the_raw_wechat_id_is_not_on_the_page_and_copy_is_in_the_menu(reader):
    page, _ = reader
    assert "wxid_" not in page.locator("header.person-head").inner_text()     # the header, contact card included
    page.locator(".inv-more > summary").first.click()
    item = page.locator(".inv-menu .copy-wechat")
    assert item.count() == 1 and item.inner_text().strip() == "Copy WeChat ID"
