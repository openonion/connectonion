"""「你这边对接的人」 on the page the Host actually serves, and no raw address as a name (#3397).

The rc23 hunt (2026-11-23 20:25) counted 「你这边对接的人」 on 0 of 73 real orgs and said the served data had no
`your_side`. Read back, the served data.json carried `your_side` on all 73 orgs (1 non-empty) and the live page drew
it once its details loaded; the count had been taken from the live shell, which is the Today build and loads org
details from /rem/data.json afterwards. This file pins that path: the live shell plus /rem/data.json, exactly the
two files the Host publishes (reader._render), so a change that drops `your_side` from either fails here.

The same hunt found the owner's own org tree naming two teammates by a raw address: their pages are titled by
it because REM does not know their names (#3157). The tree now reads the part before the @, says the name is
unknown, and keeps the address as the tooltip, like the People table.
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
SHOTS = Path(os.environ.get("REM_PR_SHOTS", "/tmp/rem-your-side-served-shots"))
CLIENT, OWN, MATE, NAMELESS = ("orgs/fernhill-labs.md", "orgs/quillmoor.md", "people/kit-brennan.md",
                               "people/dana-quillmoor-example.md")
ADDRESS = "dana@quillmoor.example"
# Teammates known only by address whose local part is not a name: a random string and a role mailbox.
ODD, ROLE = "j23x@quillmoor.example", "info@quillmoor.example"
SOURCES = "\n## Sources\n- [1] gmail:fixture:9 — 2026-09-01\n"


def _notebook(root, now):
    from rem_reader_notebook import build

    from connectonion.rem.files import Notebook
    build(root, now)
    book = Notebook(root)
    book.write(OWN, "# Quillmoor\n\n## Facts\n- What they do: Agent tools [1]\n" + SOURCES)
    book.write(MATE, "# Kit Brennan\n\n## Facts\n- Email: kit@quillmoor.example [1]\n- Role: Co-founder [1]\n" + SOURCES)
    # A teammate REM knows only by address: the page is titled by it, as on the real notebook.
    book.write(NAMELESS, f"# {ADDRESS}\n\n## Facts\n- Email: {ADDRESS} [1]\n" + SOURCES)
    for address in (ODD, ROLE):
        book.write("people/" + address.replace("@", "-").replace(".", "-") + ".md",
                   f"# {address}\n\n## Facts\n- Email: {address} [1]\n" + SOURCES)
    owner = book.read("people/avery-lin.md")
    owner = owner.replace("- Email: avery@lin.example [1]", "- Email: avery@quillmoor.example [1]", 1)
    owner = owner.replace("- Company: Unknown", "- Company: Quillmoor (co-founder) [1]", 1)
    book.write("people/avery-lin.md", owner)
    client = book.read(CLIENT)
    client = client.replace("## People here\n", "## People here\n- [Kit Brennan](../people/kit-brennan.md) — on the pilot thread [1]\n", 1)
    book.write(CLIENT, client)
    return root


@pytest.fixture
def served(tmp_path, monkeypatch):
    """The live shell at / and its details at /rem/data.json: what the Host serves (reader._render)."""
    from patchright.sync_api import sync_playwright

    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = _notebook(tmp_path / "rem", datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    live, as_of, _ = rem_reader._render(root, "live")
    full, _, _ = rem_reader._render(root, "full", as_of)
    errors, writes = [], []

    def serve(route):
        path = route.request.url[len(BASE) - 1:].split("#")[0].split("?")[0]
        if route.request.method != "GET":
            writes.append(path)
            return route.fulfill(status=200, body="{}", content_type="application/json")
        if path == "/rem/data.json":
            return route.fulfill(body=full["data.json"], content_type="application/json")
        if path.startswith("/rem/"):
            return route.fulfill(status=200, body="{}", content_type="application/json")
        if path in ("/", "/index.html"):
            return route.fulfill(body=live["live.html"], content_type="text/html")
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
            page.evaluate("""([where]) => { setInterfaceLanguage("zh"); location.hash = "r=" + encodeURIComponent(where); }""",
                          [where], isolated_context=False)
            page.locator("#main .ov-org-tree").first.wait_for()
            return page

        yield go
        browser.close()
    assert not errors, errors


def test_the_served_details_carry_your_side(tmp_path, monkeypatch):
    """data.json, built as the Host builds it, holds `your_side` on every org and names the teammate on the client."""
    import json

    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = _notebook(tmp_path / "rem", datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    full, _, _ = rem_reader._render(root, "full")
    orgs = {row["path"]: row for row in json.loads(full["data.json"])["records"] if row["category"] == "orgs"}
    assert orgs and all("your_side" in org for org in orgs.values())
    assert orgs[CLIENT]["your_side"] == [MATE]


@pytest.mark.parametrize("width", [1440, 390])
def test_the_live_page_draws_your_side_from_the_served_details(served, width):
    page = served(CLIENT, width)
    yours = page.locator("#main .ov-org-tree .ov-yours")
    yours.wait_for()
    assert page.locator("#main .ov-org-tree .ov-yours-h").inner_text().strip() == "你这边对接的人"
    assert any("Kit Brennan" in text for text in yours.locator("li").all_inner_texts())
    orgs = page.evaluate("() => REM.records.filter(r => r.category === 'orgs')", isolated_context=False)
    assert orgs and all("your_side" in org for org in orgs)


@pytest.mark.parametrize("width", [1440, 390])
def test_a_teammate_titled_by_an_address_never_reads_as_half_an_address(served, width):
    page = served(OWN, width)
    tree = page.locator("#main .ov-org-tree")
    opening = page.locator("#main .ov-opening").first.inner_text()
    assert "Dana" in opening and ADDRESS not in opening, opening

    def row(address):
        link = tree.locator(f'a[title="{address}"]').first
        return link.evaluate("a => { const item = a.closest('[role=treeitem]'); return { label: a.textContent, "
                             "note: item.querySelector('.ov-tk')?.textContent || '', aria: item.getAttribute('aria-label') }; }")

    # A name-like local part becomes the name; the address is the muted second line, never 未知姓名.
    dana = row(ADDRESS)
    assert dana["label"] == "Dana" and dana["note"] == ADDRESS, dana
    # Not a name (random string, role mailbox): the whole address is the label, and the note says only it is known.
    for address in (ODD, ROLE):
        odd = row(address)
        assert odd["label"] == address and odd["note"] == "只知道邮箱", odd
    texts = tree.locator("[role=treeitem] .ov-trow").all_inner_texts()
    assert not [text for text in texts if "未知姓名" in text], texts
    assert not [text for text in tree.locator("a").all_inner_texts() if text.endswith(("j23x", "info", "dana"))]
    SHOTS.mkdir(parents=True, exist_ok=True)
    tree.scroll_into_view_if_needed()
    page.screenshot(path=str(SHOTS / f"your-side-served-own-{width}.png"), full_page=False)
