"""An upgraded notebook shows WeChat activity, the source mark and the folds after one page build (opt in, #3368).

The state the owner's notebook was in on the day #3357 shipped: WeChat pages made by an older map, with no chat
activity, no onboarding record and nothing in the people queue. Before the fix every People row showed "—" until
a night run. Here no night runs: one page build must fill what the night would. Invented notebook.
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
SUBS = {"wechat": {"id": "wechat", "kind": "wechat", "enabled": True, "consented": True}}


def _old_map(root):
    """Pages only, as rc14's `co rem map --source wechat` left them; and the WeChat source as it reads now."""
    from connectonion.rem.files import Notebook
    book, rows = Notebook(root), []
    for i in range(12):
        handle = f"wxid_friend{i:04d}"
        book.stub_person(f"people/friend-{i:04d}-wechat.md", f"Friend {i:04d}", [handle])
        rows.append({"address": handle, "name": f"Friend {i:04d}", "mails": 0, "sent": 0, "received": 0,
                     "friend": True, "remark": False})
    for handle, name, days, mine, n90 in (("wxid_wren", "Wren Pike", 3, False, 14), ("wxid_ash", "Ash Kiln", 180, True, 0)):
        book.stub_person(f"people/{handle}.md", name, [handle])
        rows.append({"address": handle, "name": name, "mails": 40, "sent": 20, "received": 20, "friend": True,
                     "remark": True, "last": (NOW - timedelta(days=days)).isoformat(), "last_mine": mine, "n90": n90})
    return rows


@pytest.fixture(params=[1440, 390])
def reader(request, tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader
    from connectonion.rem import service
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = build(tmp_path / "rem", datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    rows = _old_map(root)
    real = service.subscriptions
    monkeypatch.setattr("connectonion.rem.service.subscriptions", lambda r: {**real(r), **SUBS})
    monkeypatch.setattr("connectonion.rem.chat.wechat_people", lambda *a, **k: [{**r, "kind": "wechat"} for r in rows])
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


def test_one_page_build_fills_activity_folds_and_the_mark_with_no_night_run(reader):
    page, width = reader
    page.goto(BASE + "#c=people")
    page.wait_for_selector(".people-table")
    row = page.locator(".people-table tbody tr", has_text="Wren Pike")
    assert row.count() == 1
    if width > 500:
        cells = [cell.strip() for cell in row.locator("td").all_inner_texts()]
        assert "14" in cells and "Them" in cells                  # WeChat activity, not "—"
    folds = page.locator("details.friend-directory summary").all_inner_texts()
    assert folds == ["WeChat friends · no chats · 12", "WeChat friends · not in 90 days · 1"]
    marks = page.evaluate("() => [...document.querySelectorAll('.people-table tbody tr .src-mark')].map(m => m.textContent)")
    assert set(marks) == {"Mail"} and row.locator(".src-mark").count() == 0
