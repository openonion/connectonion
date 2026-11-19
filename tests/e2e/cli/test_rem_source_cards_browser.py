"""#3165 deep hunt: source cards that opened empty on project pages (29/40, 32/40, 40/40 on the owner's notebook).
The live reader fetches the one original the snapshot left out; a link source offers its web page; nothing opens blank."""
import json
import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")
BASE = "http://rem.test/"
REPO = "project-source:" + "c" * 64


@pytest.fixture
def project_page(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("projects/harbour.md", "# Harbour\n\n## What it is\nHarbour reads mail into a notebook [1]. "
                         "Its release was cut on the web [2].\n\n## Sources\n- [1] " + REPO + " — 2026-10-26\n"
                         "- [2] https://github.com/example/harbour/releases/tag/v1 — 2026-10-27\n")
    html = rem_reader.render(root, local=True)
    asked = []

    def serve(route):
        path = route.request.url[len(BASE) - 1:].split("#")[0]
        if path.startswith("/rem/source"):
            asked.append(path)
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(
                {"excerpt": "Harbour reads mail and writes the notebook.", "truncated": False, "source": "project-source",
                 "time": "", "sender": "", "thread": "", "origin": "git:/repo/README.md"}))
        if path.startswith("/rem/"):
            return route.fulfill(status=200, body="{}", content_type="application/json")
        if path in ("/", "/index.html"):
            return route.fulfill(body=html, content_type="text/html")
        return route.abort()

    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US", reduced_motion="reduce")
        page = context.new_page()
        context.route("http*://**/*", serve)
        page.goto(BASE + "#r=projects%2Fharbour.md")
        page.locator(".deep-sources").wait_for()
        yield page, asked
        browser.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_a_source_the_snapshot_left_out_is_fetched_when_its_card_opens(project_page, width):
    page, asked = project_page
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    page.evaluate(f"() => {{ REM.live = true; delete REM.source_context['{REPO}']; }}", isolated_context=False)
    title = page.locator(".deep-sources li#src-1 .src-title")
    assert not __import__("re").match(r"^[0-9a-f]{16,}", title.inner_text()), title.inner_text()  # never a hash as a name
    title.click()
    panel = page.locator("#evidence-panel")
    panel.get_by_text("Harbour reads mail and writes the notebook.").wait_for(timeout=5000)
    assert len(asked) == 1 and "isn't in this snapshot" not in panel.inner_text()
    if os.environ.get("REM_PR_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["REM_PR_SHOTS"], f"cards-fetched-{width}.png"))
    page.keyboard.press("Escape")
    page.locator(".deep-sources li#src-1 .src-title").click()  # asked once: the second open reads what came back
    panel.get_by_text("Harbour reads mail and writes the notebook.").wait_for()
    assert len(asked) == 1


def test_a_link_source_without_a_copy_offers_its_web_page(project_page):
    page, asked = project_page
    page.evaluate("() => { REM.live = true; for (const k of Object.keys(REM.source_context || {})) if (k.startsWith('https:')) delete REM.source_context[k]; }",
                  isolated_context=False)
    page.route("**/rem/source?**", lambda route: route.fulfill(status=404, body="not found"))
    page.locator(".deep-sources li#src-2 .src-title").click()
    panel = page.locator("#evidence-panel")
    link = panel.get_by_role("link", name="Open the web page ↗")
    link.wait_for(timeout=5000)
    assert link.get_attribute("href") == "https://github.com/example/harbour/releases/tag/v1"
    assert "REM kept this link" in panel.inner_text()
    if os.environ.get("REM_PR_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["REM_PR_SHOTS"], "cards-weblink-1440.png"))


def test_a_profile_cards_sources_can_be_opened_by_touch(tmp_path, monkeypatch):
    """Hover-only sources were unreachable on a phone: a touch device shows them and one tap opens the card."""
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/wren-hale.md", "# Wren Hale\n\n## Facts\n- Email: wren@example.test [1]\n- Phone: +61 400 000 000 [1]\n\n"
                         "## Who they are\nWren plans the venue [1].\n\n## Sources\n- [1] gmail:18f0aa11bb22cc33\n")
    path = tmp_path / "reader.html"
    path.write_text(rem_reader.render(root, local=True))
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True).new_page()
        page.goto(path.as_uri() + "#r=people%2Fwren-hale.md")
        cite = page.locator(".person-head .pcard .pc-row .cite").first
        cite.wait_for()
        box = cite.bounding_box()
        assert box and box["width"] >= 24 and box["height"] >= 32 and cite.evaluate("n => getComputedStyle(n).opacity") != "0"
        cite.tap()
        page.locator("#evidence-panel").wait_for(state="visible")
        browser.close()
