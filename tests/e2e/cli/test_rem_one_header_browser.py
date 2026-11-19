"""One header on every record page, each fact said once (rc35 hunt, #3131 / #3165 findings 5 and 7).

Seen on the owner's real copy: the project head had a filled 调查, the organisation head an outlined 调查 and a
"查看来源 →" floating top right, the person head a grey "已是最新": three looks in the same slot. A person's
organisation was said up to five times (the line under the name, 部门, 部门职务, the tags), the same LinkedIn
profile twice, and "昨夜更新" sat beside "上次调查 昨天". The notebook is the invented one in
tests/fixtures/rem_reader_notebook.py, with duplicates planted the way the real one had them.
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
SHOTS = os.environ.get("CO_REM_SHOTS")
MARA, ORG, PROJECT = "people/mara-ostrowski.md", "orgs/fernhill-labs.md", "projects/harbour.md"
HEADS = {MARA: "#main .person-head", ORG: "#main .ov-say", PROJECT: "#main > .page-head"}


def _notebook(root, now):
    from rem_reader_notebook import build
    from connectonion.rem.files import Notebook
    build(root, now)
    book = Notebook(root)
    text = book.read(MARA)
    # The real page's shapes: the organisation again as her unit, the same LinkedIn profile as a handle and a link.
    text = text.replace("- Links: https://fernhill.example/team/mara [2]",
                        "- Links: https://fernhill.example/team/mara; https://www.linkedin.com/in/mara-ostrowski/ [2]\n"
                        "- Unit: Fernhill Labs [2]")
    text = text.replace("- Handles: mara@fernhill.example", "- Handles: linkedin.com/in/mara-ostrowski (LinkedIn)")
    assert "linkedin.com/in/mara-ostrowski (LinkedIn)" in text and "- Unit: Fernhill Labs" in text
    book.write(MARA, text)
    return root


@pytest.fixture
def reader(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    frozen = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    html = rem_reader.render(_notebook(tmp_path / "rem", frozen), local=True)
    errors = []

    def serve(route):
        path = route.request.url[len(BASE) - 1:].split("#")[0]
        if path.startswith("/rem/"):
            return route.fulfill(status=200, body="{}", content_type="application/json")
        if path in ("/", "/index.html"):
            return route.fulfill(body=html, content_type="text/html")
        return route.abort()

    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US", reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        page.goto(BASE)
        page.locator(".night-card .count").wait_for()

        def open_page(path, width=1440, label="current"):
            page.set_viewport_size({"width": width, "height": 900})
            # Every page in the same investigate state, and Mara tagged with her own organisation and a topic.
            page.evaluate("""([path, label]) => { REM.live = true; setInterfaceLanguage("zh");
              REM.tags = { ...(REM.tags || {}), "fernhill-labs": { label: "Fernhill Labs", page: "orgs/fernhill-labs.md", count: 3 },
                pilot: { label: "pilot", count: 2 } };
              for (const r of REM.records) if (["people/mara-ostrowski.md", "orgs/fernhill-labs.md", "projects/harbour.md"].includes(r.path)) {
                r.investigation = { label, last: "2026-09-30", new_mails: label === "update" ? 2 : 0, new_sessions: 0, leads: label === "deeper" ? 3 : 0 };
                r.tags = ["fernhill-labs", "pilot"]; }
              location.hash = "#r=" + encodeURIComponent(path); render(); }""", [path, label], isolated_context=False)
            page.locator("#main h1").first.wait_for()
            return page

        try:
            yield open_page
        finally:
            browser.close()
    assert not errors, errors


SLOT = """sel => { const head = document.querySelector(sel), acts = head && head.querySelector('.rec-acts');
  if (!acts) return null;
  const go = acts.querySelector('.inv-go'), src = acts.querySelector('.rec-sources'), s = go && getComputedStyle(go);
  return { order: [...acts.children].map(n => n.className.split(' ')[0]), label: go && go.textContent.trim(),
    disabled: go && go.disabled, title: go && go.title, bg: s && s.backgroundColor, radius: s && s.borderRadius, height: s && s.height,
    sources: src && src.textContent.trim(), stray: document.querySelectorAll('#main :is(.ov-source-action, .focus-source)').length }; }"""


@pytest.mark.parametrize("label", ["current", "deeper"])
def test_person_org_and_project_heads_share_one_action_slot(reader, label):
    slots = {}
    for path, head in HEADS.items():
        page = reader(path, label=label)
        slots[path] = page.evaluate(SLOT, head, isolated_context=False)
        assert slots[path], f"{path}: no shared action slot in its head"
    first = slots[MARA]
    for path, slot in slots.items():
        # The same control, the same look, in the same order: 调查 first, then where its sources are.
        assert slot["order"] == first["order"], (path, slot["order"], first["order"])
        assert (slot["bg"], slot["radius"], slot["height"]) == (first["bg"], first["radius"], first["height"]), (path, slot, first)
        assert slot["label"] == "调查", (path, slot["label"])
        assert slot["stray"] == 0, f"{path}: a second 查看来源 outside the slot"
    if label == "current":
        # Nothing new is the same button, off, with the reason as its tooltip; not a different grey control.
        assert all(slot["disabled"] and slot["title"] for slot in slots.values()), slots
    else:
        assert not any(slot["disabled"] for slot in slots.values()), slots


def test_each_fact_once_in_the_person_header(reader):
    page = reader(MARA)
    header = page.evaluate("""() => { const head = document.querySelector('#main .person-head');
      const text = head.innerText, hrefs = [...head.querySelectorAll('a[href^="http"]')].map(a => a.href);
      const tags = [...head.querySelectorAll('.tag-link')].map(a => a.textContent.trim());
      const norm = u => u.toLowerCase().replace(/^https?:\\/\\//, '').replace(/^www\\./, '').replace(/[?#].*$/, '').replace(/\\/$/, '');
      const linkedin = [...head.querySelectorAll('.pc-item, a')].map(n => n.textContent).filter(t => /linkedin\\.com\\/in\\/mara/i.test(t));
      return { org: (text.match(/Fernhill Labs/g) || []).length, tags, urls: hrefs.map(norm), linkedin: linkedin.length,
        freshness: (text.match(/昨夜更新|上次调查|上次 /g) || []).length }; }""", isolated_context=False)
    assert header["org"] == 1, header
    assert "Fernhill Labs" not in header["tags"] and "pilot" in header["tags"], header
    assert len(header["urls"]) == len(set(header["urls"])), header
    assert header["linkedin"] <= 1, header
    assert header["freshness"] <= 1, header


@pytest.mark.parametrize("width", [1440, 390])
def test_the_heads_screenshot_and_fit(reader, width):
    wrong = []
    for path, head in HEADS.items():
        page = reader(path, width=width)
        if SHOTS:
            page.screenshot(path=str(Path(SHOTS) / f"one-header-{path.split('/')[0]}-{width}.png"))
        if not page.evaluate("() => document.documentElement.scrollWidth <= innerWidth + 1", isolated_context=False):
            wrong.append((path, "scrolls sideways"))
        if page.locator(head + " .rec-acts").count() != 1:
            wrong.append((path, "no action slot"))
    assert not wrong, wrong
