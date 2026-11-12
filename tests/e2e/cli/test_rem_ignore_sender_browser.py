"""忽略 an advertiser once and their mail never reaches Today again (sprint 13, opt in).

Owner, 2026-11-13: «忽略和标记完成很重要，有的任务就是线下说了，或者现在不需要处理，或者广告要忽略», and «你要有个文字按钮».
The invented notebook (tests/fixtures/rem_reader_notebook.py) gains a shop that mails offers. The page is
rebuilt from the notebook on every load, and /rem/thread and /rem/sender write the notebook as the Host does,
so a reload shows what the next build would.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
SHOP, AD = "orgs/sale-shop.md", "deals@sale-shop.example"


def _offer(root, number, words):
    """One more offer from the shop: its mail in rem.db and the line the night would write."""
    page = root / SHOP
    text = page.read_text() if page.exists() else "# Sale Shop\n\n## Open threads\n\n## Sources\n"
    head, _, sources = text.partition("## Sources\n")
    page.write_text(head.rstrip("\n") + f"\n- You owe Sale Shop a reply about the {words}. [{number}]\n\n"
                    f"## Sources\n{sources}- [{number}] gmail:offer{number} — offer; confidence high; observed 2026-10-01.\n")
    with sqlite3.connect(root / ".state" / "rem.db") as db:
        db.execute("insert into messages (id, source, thread, sender, recipients, time, subject, body_path) values (?, ?, ?, ?, ?, ?, ?, ?)",
                   (f"gmail:offer{number}", "gmail", f"mail:gmail:offer{number}", AD, json.dumps(["Avery"]),
                    "2026-10-01T08:00:00+00:00", "Offer", None))


@pytest.fixture
def reader(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader, threads
    from connectonion.rem.today import queue
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    frozen = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    snapshot = rem_reader.snapshot

    def fixed_snapshot(root, local=False, today=False):
        data = snapshot(root, local, today=today)
        data["as_of"] = frozen.isoformat()
        data["today_queue"] = queue(root, records=data["records"], contexts=data["source_context"], states=data["threads"], as_of=frozen.date())
        return data

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    root = build(tmp_path / "rem", frozen)
    _offer(root, 1, "spring sale")
    calls, errors = [], []

    def serve(route):
        request = route.request
        path = request.url[len(BASE) - 1:].split("#")[0]
        if path in ("/", "/index.html"):
            return route.fulfill(body=rem_reader.render(root, local=True), content_type="text/html")
        body = json.loads(request.post_data or "{}") if request.method == "POST" else None
        calls.append((path, body))
        if path == "/rem/thread" and body:
            reply = threads.set_state(root, body["key"], body["state"], device=body.get("device"), keys=body.get("keys"))
        elif path == "/rem/sender":
            reply = {"ignored": threads.ignore_sender(root, body["address"], ignored=body["ignored"])}
        else:
            reply = {}
        return route.fulfill(status=200, body=json.dumps(reply), content_type="application/json")

    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US", reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        yield page, root, calls
        browser.close()
    assert not errors, errors


def _open(page, language):
    page.goto(BASE)
    page.locator(".night-card .count").wait_for()
    page.evaluate(f"() => {{ REM.live = true; setInterfaceLanguage('{language}'); dealCard('{SHOP}'); scrollTo(0, 0); }}",
                  isolated_context=False)


def _notice_says(page, words):
    """The notice changes after the Host answers; wait for its words, then read them."""
    page.wait_for_function("words => (document.getElementById('done-notice')?.innerText || '').startsWith(words)", arg=words, timeout=5000)
    return True


def _today(page):
    return page.locator("#main .today-brief").inner_text()


@pytest.mark.parametrize("size", [(1440, 900), (390, 844)])
def test_ignore_offers_to_stop_the_sender_and_a_new_offer_never_reaches_today(reader, size):
    page, root, calls = reader
    page.set_viewport_size({"width": size[0], "height": size[1]})
    _open(page, "zh")
    row = page.locator(f'#main .today-brief .qcard[data-path="{SHOP}"] .qitem:visible').first
    assert "spring sale" in row.inner_text()
    row.get_by_role("button", name="忽略", exact=True).click()
    notice = page.locator("#done-notice")
    stop = notice.get_by_role("button", name=f"以后不再显示 {AD} 的邮件")
    assert stop.is_visible() and notice.inner_text().startswith("已忽略 · 这一条不会再回来 · 撤销 · 以后不再显示")
    box = stop.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= size[0]
    stop.click()
    assert _notice_says(page, f"已忽略 · 以后不再显示 {AD} 的邮件 · 撤销 · 已保存到笔记本")
    assert [body for path, body in calls if path == "/rem/sender"] == [{"address": AD, "ignored": True}]
    assert AD in (root / ".state" / "ignored-senders.txt").read_text()

    # The shop writes again; the next build leaves the new offer out of Today.
    _offer(root, 2, "winter sale")
    _open(page, "zh")
    assert "winter sale" not in _today(page) and "spring sale" not in _today(page)

    # Settings names the sender in words and lets them back in.
    page.evaluate("() => openSettings()", isolated_context=False)
    listed = page.locator("#settings .set-ignored")
    assert listed.locator(".set-k").inner_text() == "已忽略的发件人" and AD in listed.inner_text()
    listed.get_by_role("button", name="恢复显示").click()
    page.locator("#settings .set-ignored").wait_for(state="detached")
    _open(page, "zh")
    assert "winter sale" in _today(page)


def test_undo_on_the_notice_reopens_the_item_and_lets_the_sender_back(reader):
    page, root, calls = reader
    _open(page, "en")
    row = page.locator(f'#main .today-brief .qcard[data-path="{SHOP}"] .qitem:visible').first
    row.get_by_role("button", name="Ignore", exact=True).click()
    page.locator("#done-notice").get_by_role("button", name=f"Stop showing mail from {AD}").click()
    notice = page.locator("#done-notice")
    assert _notice_says(page, f"Ignored · mail from {AD} no longer shows here · Undo")
    notice.get_by_role("button", name="Undo").click()
    page.wait_for_function("() => !document.getElementById('done-notice')")
    page.wait_for_timeout(300)
    assert (root / ".state" / "ignored-senders.txt").read_text().count("@") == 0
    _open(page, "en")
    assert "spring sale" in _today(page)


def test_a_row_with_no_mail_sender_offers_nothing_more_than_its_own_ignore(reader):
    page, _, _ = reader
    _open(page, "en")
    page.evaluate("() => dealCard('people/ines-halvorsen.md')", isolated_context=False)
    row = page.locator('#main .today-brief .qcard[data-path="people/ines-halvorsen.md"] .qitem:visible').first
    row.get_by_role("button", name="Ignore", exact=True).click()
    assert page.locator("#done-notice .sender-ignore").count() == 0
