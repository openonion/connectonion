"""不是人 moves an assistant out of People in one click, Undo brings it back, and 是人 lets one back in (opt in).

rc35 check (Mac session): a company's assistant, writing from the company's domain, still led People. Its company's
page names it as the assistant, so it starts in the folded agents and services group; any other row has 不是人,
which the Host stores as one dated line (threads.mark_person) that the next build reads. The page here is rebuilt
from the invented notebook on every load, and /rem/person writes it as the Host does.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
KILN = ("# Kiln\n\n## Domains\n- kiln.example [1]\n\n## Facts\n"
        "- What they do: Provides Kiln, an AI assistant service that answers mail for its users. [1]\n"
        "- Your contacts: [Pia Grove](../people/pia-grove.md) and Kiln's automated “Ember” assistant. [1]\n")


def _person(name, address):
    return f"# {name}\n\n{name} wrote about the pilot [1].\n\n## Contact\n- Email: {address} [1]\n- Role: Unknown\n\n## Sources\n- [1] gmail:a1b2c3d4e5f6 — invented\n"


@pytest.fixture(params=[1440, 390])
def reader(request, tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader, threads
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    frozen = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    root = build(tmp_path / "rem", frozen)
    (root / "orgs/kiln.md").write_text(KILN)
    (root / "people/ember.md").write_text(_person("Ember", "ember@kiln.example"))
    (root / "people/pia-grove.md").write_text(_person("Pia Grove", "pia@kiln.example"))
    (root / "people/ody-lark.md").write_text(_person("Ody Lark", "ody@lark.example"))
    calls, errors = [], []

    def serve(route):
        request = route.request
        path = request.url[len(BASE) - 1:].split("#")[0]
        if path in ("/", "/index.html"):
            return route.fulfill(body=rem_reader.render(root, local=True), content_type="text/html")
        body = json.loads(request.post_data or "{}") if request.method == "POST" else None
        calls.append((path, body))
        reply = {"marks": threads.mark_person(root, body["address"], person=body["person"])} if path == "/rem/person" else {}
        return route.fulfill(status=200, body=json.dumps(reply), content_type="application/json")

    width = request.param
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": width, "height": 900 if width > 500 else 844}, locale="en-US",
                                      reduced_motion="reduce", is_mobile=width < 500, has_touch=width < 500)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        yield page, root, calls, width
        browser.close()
    assert not errors, errors


def _people(page):
    page.goto(BASE + "#c=people")
    page.locator(".people-table tbody tr").first.wait_for()
    page.evaluate("() => { REM.live = true; render(); }", isolated_context=False)
    page.locator(".people-table tbody tr").first.wait_for()
    return page.locator(".people-table td.c-name a").all_inner_texts()


def _topmost(page, locator):
    # Centred, as a thumb brings it: the phone's tab bar covers the last 50px of any page by design.
    locator.evaluate("node => node.scrollIntoView({block: 'center'})")
    box = locator.bounding_box()
    return page.evaluate("([x, y, sel]) => !!document.elementFromPoint(x, y)?.closest(sel)",
                         [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, ".not-person, .is-person, .person-mark"], isolated_context=False)


def test_the_assistant_its_company_names_starts_outside_people(reader):
    page, _, _, _ = reader
    names = _people(page)
    assert "Ember" not in names and "Pia Grove" in names and "Ody Lark" in names
    group = page.locator(".machine-directory")
    assert "1 agents and services found in mail" in group.locator("summary").inner_text()


def test_not_a_person_moves_a_row_out_undo_brings_it_back_and_a_person_lets_it_in(reader):
    page, root, calls, width = reader
    _people(page)
    row = page.locator(".people-table tbody tr", has_text="Ody Lark")
    row.hover() if width > 500 else None
    button = row.locator(".not-person")
    assert button.inner_text() == "Not a person"
    box = button.bounding_box()
    assert box["height"] >= (44 if width < 500 else 28) and _topmost(page, button)
    button.click()
    page.wait_for_function("() => (document.getElementById('done-notice')?.innerText || '').startsWith('Moved out of People')", timeout=5000)
    assert "Ody Lark" not in page.locator(".people-table td.c-name a").all_inner_texts()
    assert calls[-1] == ("/rem/person", {"address": "ody@lark.example", "person": False})
    assert "not-person ody@lark.example" in (root / ".state" / "people-marks.txt").read_text()
    # A reload reads the notebook: still out of People, now in the agents and services group.
    assert "Ody Lark" not in _people(page)
    page.locator(".machine-directory summary").click()
    back = page.locator(".machine-directory tr", has_text="ody@lark.example").locator(".is-person")
    assert _topmost(page, back) and back.bounding_box()["height"] >= 44
    back.click()
    page.wait_for_function("() => (document.getElementById('done-notice')?.innerText || '').startsWith('Back in People')", timeout=5000)
    assert "Ody Lark" in page.locator(".people-table td.c-name a").all_inner_texts()
    assert "person ody@lark.example" in (root / ".state" / "people-marks.txt").read_text()


def test_undo_takes_the_mark_back(reader):
    page, root, calls, width = reader
    _people(page)
    row = page.locator(".people-table tbody tr", has_text="Ody Lark")
    row.hover() if width > 500 else None
    row.locator(".not-person").click()
    undo = page.locator("#done-notice button", has_text="Undo")
    undo.wait_for()
    undo.click()
    page.wait_for_function("() => [...document.querySelectorAll('.people-table td.c-name a')].some(a => a.textContent === 'Ody Lark')", timeout=5000)
    assert calls[-1] == ("/rem/person", {"address": "ody@lark.example", "person": None})
    assert "ody@lark.example" not in (root / ".state" / "people-marks.txt").read_text()


def _menu_item(page, record, mark):
    """The person page's header ⋯, opened, and its 不是人 / 是人 item (#3339: it lives in the menu, not the header)."""
    page.evaluate("record => { location.hash = '#r=' + encodeURIComponent(record); }", record, isolated_context=False)
    more = page.locator(".hero-acts .inv-more > summary")
    more.wait_for()
    more.click()
    item = page.locator(f".hero-acts .inv-menu .person-mark[data-mark='{mark}']")
    item.wait_for()
    return item


def test_the_person_page_has_not_a_person_in_its_header_menu(reader):
    page, _, _, width = reader
    _people(page)
    item = _menu_item(page, "people/ody-lark.md", "not-person")
    assert item.locator("xpath=.").inner_text().startswith("Not a person")
    assert _topmost(page, item)
    assert page.locator(".hero-acts > .not-person").count() == 0   # no lone word under the header's links


QI_WEN = ("# Qi Wen\n\nQi Wen asked about renting the studio [1].\n\n## Contact\n- Handles: wxid_qiwen [1]\n"
          "- Also known as: Qi Wen\n- Role: Unknown\n\n## Sources\n- [1] wechat:wxid_qiwen — invented\n")


def test_a_wechat_only_page_has_not_a_person_and_it_marks_the_wechat_id(reader):
    # #3339: a page with no mail address (a WeChat contact) had no 不是人, since the mark took only an address.
    page, root, calls, width = reader
    (root / "people/qi-wen.md").write_text(QI_WEN)
    assert "Qi Wen" in _people(page)
    item = _menu_item(page, "people/qi-wen.md", "not-person")
    assert _topmost(page, item)
    item.click()
    page.wait_for_function("() => (document.getElementById('done-notice')?.innerText || '').startsWith('Moved out of People')", timeout=5000)
    assert calls[-1] == ("/rem/person", {"address": "wxid_qiwen", "person": False})   # the handle, never the name
    assert "not-person wxid_qiwen" in (root / ".state" / "people-marks.txt").read_text()
    # The same menu now offers 是人, and after a reload the notebook agrees: out of People, in agents and services.
    assert _menu_item(page, "people/qi-wen.md", "person").count() == 1
    assert "Qi Wen" not in _people(page)
    page.locator(".machine-directory summary").click()
    back = page.locator(".machine-directory tr", has_text="wxid_qiwen").locator(".is-person")
    assert _topmost(page, back)
