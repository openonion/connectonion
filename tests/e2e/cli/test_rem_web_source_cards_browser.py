"""rc35 hunt: a web source (the OSINT enrich's links) showed its URL-encoded search query as its name, and its card
opened with the header alone: the saved capture's context had no kind, so the card's redraw threw. A web row names
the page and its site; its card says which page, when REM read it, what it said, and links to it."""
import json
import os
import re

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")
BASE = "http://rem.test/"
SEARCH = "https://duckduckgo.com/?q=%22Mira%20Vale%22%20%22Atlas%22"
TEAM = "https://www.example.org/team"


def notebook(tmp_path):
    from connectonion.rem import evidence
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    root = tmp_path / "rem"
    prepare(root)
    text = ("# Mira Vale\n\n## Who they are\nMira leads Atlas [1]. She was named on a search [2].\n\n## Sources\n"
            f"- [1] {TEAM} — 2026-11-06\n- [2] {SEARCH} — 2026-11-17\n")
    Notebook(root).write("people/mira-vale.md", text)
    task = tmp_path / "task"
    (task / "web").mkdir(parents=True)
    (task / "web" / "team.md").write_text(f"URL: {TEAM}\nTitle: Atlas team — Example\n\nMira Vale leads the Atlas project.\n")
    (task / "web" / "sources.json").write_text(json.dumps([{"url": TEAM, "file": "team.md", "date": "2026-11-06"}]))
    evidence.retain_research(root, text, evidence.research_items(task))
    return root


@pytest.fixture
def person_page(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    html = rem_reader.render(notebook(tmp_path), local=True)
    replies = {"source": (404, "not found")}

    def serve(route):
        path = route.request.url[len(BASE) - 1:].split("#")[0]
        if path.startswith("/rem/source"):
            status, body = replies["source"]
            return route.fulfill(status=status, content_type="application/json", body=body)
        if path.startswith("/rem/"):
            return route.fulfill(status=200, body="{}", content_type="application/json")
        if path in ("/", "/index.html"):
            return route.fulfill(body=html, content_type="text/html")
        return route.abort()

    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US", reduced_motion="reduce")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        page.goto(BASE + "#r=people%2Fmira-vale.md")
        page.locator(".deep-sources").wait_for()
        # rem.test is not loopback, so the reader starts at Public only (#2840); these cards are read at Cover sensitive.
        page.evaluate("() => setPrivacy('cover', {save: false})", isolated_context=False)
        yield page, replies, errors
        browser.close()


def test_a_web_row_names_the_page_and_its_site_never_an_encoded_query(person_page):
    page, _, _ = person_page
    rows = {n: page.locator(f".deep-sources li#src-{n}") for n in ("1", "2")}
    titles = {n: row.locator(".src-title").inner_text() for n, row in rows.items()}
    assert not any(re.search(r"%[0-9A-F]{2}", title, re.I) for title in titles.values()), titles
    assert titles["1"] == "Atlas team — Example"
    assert titles["2"] == 'DuckDuckGo search: "Mira Vale" "Atlas"'
    assert "example.org" in rows["1"].locator(".src-meta").inner_text()
    assert "duckduckgo.com" in rows["2"].locator(".src-meta").inner_text()


def assert_card_on_top_and_closes(page, trigger):
    panel = page.locator("#evidence-panel")
    box = panel.bounding_box()
    for x, y in ((box["x"] + 12, box["y"] + 12), (box["x"] + box["width"] - 12, box["y"] + box["height"] / 2)):
        assert page.evaluate("([x, y]) => document.getElementById('evidence-panel').contains(document.elementFromPoint(x, y))",
                             [x, y], isolated_context=False), (x, y)
    page.keyboard.press("Escape")
    panel.wait_for(state="hidden")
    assert page.evaluate("() => document.activeElement?.classList.contains('src-title')", isolated_context=False)


@pytest.mark.parametrize("width", [1440, 390])
def test_a_saved_web_page_opens_with_its_title_words_day_and_link(person_page, width):
    page, _, errors = person_page
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    title = page.locator(".deep-sources li#src-1 .src-title")
    title.click()
    panel = page.locator("#evidence-panel")
    panel.get_by_text("Mira Vale leads the Atlas project.").wait_for(timeout=5000)
    text = panel.inner_text()
    assert "Atlas team — Example" in text and "example.org" in text and "Nov 6" in text, text
    assert "URL:" not in text and text.count("Atlas team — Example") == 1, text  # co fetch's header is not repeated
    link = panel.get_by_role("link", name="Open the web page ↗")
    assert link.get_attribute("href") == TEAM and link.get_attribute("target") == "_blank"
    assert "noopener" in link.get_attribute("rel")
    assert errors == []
    if os.environ.get("REM_PR_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["REM_PR_SHOTS"], f"web-card-saved-{width}.png"))
    assert_card_on_top_and_closes(page, title)


def test_a_web_page_fetched_from_an_older_host_still_opens_with_a_body(person_page):
    """An older Host's /rem/source answers a web capture with excerpt and truncated alone. The redraw threw on the
    missing kind, leaving the header alone (the rc35 hunt's empty web cards)."""
    page, replies, errors = person_page
    replies["source"] = (200, json.dumps({"excerpt": "Mira Vale leads the Atlas project.", "truncated": False}))
    page.evaluate(f"() => {{ REM.live = true; delete REM.source_context['{TEAM}']; }}", isolated_context=False)
    page.locator(".deep-sources li#src-1 .src-title").click()
    panel = page.locator("#evidence-panel")
    panel.get_by_text("Mira Vale leads the Atlas project.").wait_for(timeout=5000)
    assert panel.get_by_role("link", name="Open the web page ↗").get_attribute("href") == TEAM
    assert errors == []


@pytest.mark.parametrize("width", [1440, 390])
def test_a_search_link_without_a_copy_says_so_and_links_to_it(person_page, width):
    page, _, errors = person_page
    page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
    page.evaluate("() => { REM.live = true; }", isolated_context=False)
    title = page.locator(".deep-sources li#src-2 .src-title")
    title.click()
    panel = page.locator("#evidence-panel")
    link = panel.get_by_role("link", name="Open the web page ↗")
    link.wait_for(timeout=5000)
    text = panel.inner_text()
    assert 'DuckDuckGo search: "Mira Vale" "Atlas"' in text and "REM kept this link" in text, text
    assert link.get_attribute("href") == SEARCH and errors == []
    if os.environ.get("REM_PR_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["REM_PR_SHOTS"], f"web-card-link-{width}.png"))
    assert_card_on_top_and_closes(page, title)


def test_zh_names_a_search_in_chinese(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    path = tmp_path / "reader.html"
    path.write_text(rem_reader.render(notebook(tmp_path), local=True))
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN").new_page()
        page.goto(path.as_uri() + "#r=people%2Fmira-vale.md")
        title = page.locator(".deep-sources li#src-2 .src-title")
        title.wait_for()
        assert title.inner_text() == 'DuckDuckGo 搜索：“Mira Vale” “Atlas”'
        browser.close()
