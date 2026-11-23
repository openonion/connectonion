"""「你这边对接的人」 on pages shaped like the owner's real ones (#3397 reopened).

The rc21 hunt (2026-11-23): on the real notebook 0 of 73 orgs showed 「你这边对接的人」, and the owner's own
teammate still sat inside a client's 人物与组织结构. #3400's rule needed the teammate's page to name the
owner's company, the owner page to link it, or an org to say Kind: own_company. Real pages do none of these:
the owner's Company is plain text, and a teammate's page carries only an Email at the owner's domain.
The notebook is the invented one in tests/fixtures/rem_reader_notebook.py; every name below is invented.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
SHOTS = Path(os.environ.get("REM_PR_SHOTS", "/tmp/rem-your-side-real-shots"))
CLIENT, OWN, MATE = "orgs/fernhill-labs.md", "orgs/quillmoor.md", "people/kit-brennan.md"
SOURCES = "\n## Sources\n- [1] gmail:fixture:9 — 2026-09-01\n"


def _notebook(root, now):
    from rem_reader_notebook import build

    from connectonion.rem.files import Notebook
    build(root, now)
    book = Notebook(root)
    # No Kind line, as on the real owner's org page.
    book.write(OWN, "# Quillmoor\n\n## Facts\n- What they do: Agent tools [1]\n" + SOURCES)
    # No Company line: only an Email at the owner's work domain, as on real teammates' pages.
    book.write(MATE, "# Kit Brennan\n\n## Facts\n- Email: kit@quillmoor.example [1]\n- Role: Co-founder [1]\n" + SOURCES)
    owner = book.read("people/avery-lin.md")
    owner = owner.replace("- Email: avery@lin.example [1]", "- Email: avery@quillmoor.example [1]", 1)
    # Plain text, not a link.
    owner = owner.replace("- Company: Unknown", "- Company: Quillmoor (co-founder) [1]", 1)
    book.write("people/avery-lin.md", owner)
    client = book.read(CLIENT)
    client = client.replace("## People here\n", "## People here\n- [Kit Brennan](../people/kit-brennan.md) — on the pilot thread [1]\n", 1)
    book.write(CLIENT, client)
    return root


@pytest.fixture
def reader(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright

    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    html = rem_reader.render(_notebook(tmp_path / "rem", datetime(2026, 10, 1, 12, tzinfo=timezone.utc)), local=True)
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
        page.locator(".night-card .count, #main h1").first.wait_for()

        def go(where, width=1440):
            page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
            page.evaluate("""([where]) => { setInterfaceLanguage("zh"); location.hash = href(byPath(where)).slice(1); render(); }""",
                          [where], isolated_context=False)
            page.locator("#main h1").first.wait_for()
            return page

        yield go
        browser.close()
    assert not errors, errors


@pytest.mark.parametrize("width", [1440, 390])
def test_a_teammate_known_only_by_the_owners_mail_domain_is_your_side(reader, width):
    page = reader(CLIENT, width)
    root = page.locator("#main .ov-org-tree [role=treeitem][aria-level='1']").first
    inside = root.locator("[role=treeitem]").all_inner_texts()
    assert not [text for text in inside if "Kit Brennan" in text], inside
    yours = page.locator("#main .ov-org-tree .ov-yours")
    assert page.locator("#main .ov-org-tree .ov-yours-h").inner_text().strip() == "你这边对接的人"
    assert any("Kit Brennan" in text for text in yours.locator("li").all_inner_texts())
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.locator("#main .ov-org-tree").scroll_into_view_if_needed()
    page.screenshot(path=str(SHOTS / f"your-side-real-{width}.png"), full_page=False)


def test_the_teammate_sits_in_the_owners_own_org(reader):
    page = reader(OWN)
    people = page.evaluate("() => REM.records.find(r => r.path === 'orgs/quillmoor.md').people", isolated_context=False)
    assert MATE in people
