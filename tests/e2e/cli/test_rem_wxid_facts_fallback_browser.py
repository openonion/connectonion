"""A chat-only person page with no known fact never shows a raw WeChat id anywhere (#3372; opt in).

#3374 moved the id out of the profile card. But a WeChat friend the night has not investigated knows no fact
but the id, so the profile card is empty and the page falls back to the older facts card. On the owner's
notebook (rc18, 1,009 pages) that card printed the id twice, under Handles and Also known as, counted it as
"2 known", and listed Last contact as not found while the header gave the date. Here every card and section is
checked, with the page's visible text and its titles, and Last contact is the chat's date. Invented notebook.
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
LAST = (NOW - timedelta(days=3)).isoformat()
IDS = ("wxid_wrenpike99", "ivymoss_77")


def _friends(root):
    from connectonion.rem import onboard
    from connectonion.rem.files import Notebook, state_path, write_json
    book = Notebook(root)
    # The WeChat map's stub: the id is the only fact, seeded into Handles and Also known as both.
    book.stub_person("people/wren-pike.md", "Wren Pike", ["wxid_wrenpike99"])
    # A friend who chose a custom WeChat id: a bare handle, still an id on a WeChat page.
    book.stub_person("people/ivy-moss.md", "Ivy Moss", ["ivymoss_77"])
    write_json(state_path(root, onboard.ACTIVITY), {
        "wxid_wrenpike99": {"last": LAST, "mine": False, "n90": 5, "total": 9},
        "ivymoss_77": {"last": LAST, "mine": True, "n90": 2, "total": 2}})


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
        yield page
        browser.close()
    assert not errors, errors


def _open(page, record):
    page.goto(BASE + "#r=" + record.replace("/", "%2F"))
    page.wait_for_selector(".r4-name")
    # Every fold open, so a section that hides the id until clicked is checked too.
    page.evaluate("() => document.querySelectorAll('details').forEach(d => d.open = true)")
    page.wait_for_timeout(150)


# Visible words, every element's title and aria-label: what a reader can see or hover. The page's data script is not.
SEEN = """() => {
  const main = document.querySelector('main') || document.body;
  const labels = [...main.querySelectorAll('[title],[aria-label]')].map(n => (n.title || '') + ' ' + (n.getAttribute('aria-label') || ''));
  const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT), texts = [];
  while (walker.nextNode()) if (!walker.currentNode.parentElement.closest('script,style,template')) texts.push(walker.currentNode.data);
  return [main.innerText, texts.join(' '), labels.join(' ')].join('\\n');
}"""


@pytest.mark.parametrize("record,wxid", [("people/wren-pike.md", IDS[0]), ("people/ivy-moss.md", IDS[1])])
def test_no_raw_wechat_id_on_a_page_that_knows_no_fact(reader, record, wxid):
    page = reader
    _open(page, record)
    seen = page.evaluate(SEEN)
    assert wxid not in seen
    assert "wxid_" not in seen


def test_the_facts_card_counts_no_id_and_gives_the_chat_date(reader):
    page = reader
    _open(page, "people/wren-pike.md")
    panel = page.locator(".panel:has(.factlist)")
    assert panel.count() == 1
    text = panel.inner_text()
    assert "Handles" not in text and "Also known as" not in text      # the id is not a fact to count
    assert "1 of" in text                                              # the one known fact: when you last talked
    assert "Last contact" in text and "3 days ago" in text             # the chat's date, said as the reader says dates
    missing = page.locator(".fact-missing")
    assert not missing.count() or "Last contact" not in missing.inner_text()
