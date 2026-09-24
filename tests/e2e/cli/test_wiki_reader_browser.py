"""Opt-in file:// browser acceptance; no server, model, or private sources."""

import os
from pathlib import Path

import pytest

from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook
from connectonion.wiki.reader import write_reader

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_WIKI_BROWSER_TEST") != "1",
    reason="opt in with CO_WIKI_BROWSER_TEST=1; requires installed Chrome",
)


def test_file_reader_navigation_search_and_mobile(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright

    monkeypatch.setattr("connectonion.wiki.service.mail_available", lambda kind: False)
    root = tmp_path / "wiki"
    prepare(root)
    notebook = Notebook(root)
    notebook.write("projects/aurora.md", "# Aurora\n\nA synthetic project.\n\n"
                   "Related: [Storage](../decisions/storage.md)\nSources: codex:test:1\n")
    notebook.write("decisions/storage.md", "# Storage\n\nMarkdown for inspectability.\n\n"
                   "<script>window.wikiInjected=true</script>\nSources: codex:test:2\n")
    page_path = write_reader(root)
    shots = Path(os.environ.get("CO_WIKI_SHOTS", str(tmp_path / "shots")))
    shots.mkdir(parents=True, exist_ok=True)
    errors, network = [], []
    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: network.append(request.url)
                    if request.url.startswith(("http:", "https:")) else None)
            page.route("http://**/*", lambda route: route.abort())
            page.route("https://**/*", lambda route: route.abort())
            page.goto(page_path.as_uri())
            page.get_by_role("heading", name="What your assistant knows").wait_for()
            page.screenshot(path=str(shots / "wiki-desktop.png"), full_page=True)
            page.locator("#main").get_by_role("link", name="Aurora", exact=True).click()
            page.locator("#main").get_by_role("link", name="Storage", exact=True).click()
            page.get_by_role("heading", name="Storage", exact=True).wait_for()
            assert "inspectability" in page.locator("#main").inner_text()
            assert page.evaluate("window.wikiInjected === undefined")
            page.locator("input[type=search]").fill("inspectability")
            page.locator("#main").get_by_role("link", name="Storage", exact=True).wait_for()
            page.set_viewport_size({"width": 375, "height": 812})
            page.screenshot(path=str(shots / "wiki-mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors, errors
            assert not network, network
        finally:
            browser.close()


def test_reader_runs_inside_opaque_wiki_iframe(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright

    monkeypatch.setattr("connectonion.wiki.service.mail_available", lambda kind: False)
    root = tmp_path / "wiki"
    prepare(root)
    Notebook(root).write("projects/example.md", "# Example\n\nA private page.\n")
    html = write_reader(root).read_text(encoding="utf-8")
    csp = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
           "script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; "
           "connect-src 'none'; form-action 'none'; base-uri 'none'\">")
    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_content('<iframe sandbox="allow-scripts" style="width:100vw;height:100vh"></iframe>')
        page.locator("iframe").evaluate("(frame, content) => frame.srcdoc = content",
                                         html.replace("<head>", "<head>" + csp))
        frame = page.frame_locator("iframe")
        frame.get_by_role("heading", name="What your assistant knows").wait_for()
        assert frame.get_by_role("link", name="Example").is_visible()
        assert frame.locator("body").evaluate("body => getComputedStyle(body).fontFamily")
        browser.close()


@pytest.fixture
def reader_page(tmp_path):
    """Synthetic snapshot, real offline template; no user notebooks or services."""
    import json
    from patchright.sync_api import sync_playwright
    from connectonion.wiki.reader import TEMPLATE, PLACEHOLDER

    literal = "Before\nSources: literal source\n\n\nRelated: literal relation\nAfter"
    diagram = "+------------" * 18 + "+\n" + "| stage      " * 18 + "|"
    text = ("# Layout fixture\n\n## Overview\n\nSynthetic notes.\n\n"
            "```text\n" + literal + "\n```\n\n"
            "~~~python\ndef hello():\n    return '<safe>'\n~~~\n\n"
            "````text\n```\nSources: still code\n````\n\n"
            "```text\n" + diagram + "\n```\n\n"
            "`" + "a" * 160 + "`\n\n"
            "| Component | Input | Output | Owner | Status | Action |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| Collection | Sessions | Markdown | Research | Ready | Verify provenance |\n\n"
            "1. Review sources\n   - Check permissions\n   - Inspect history\n"
            "2. Write summary\n   - Record evidence\n   - Link decisions\n\n"
            "<script>window.wikiInjected=true</script>\n\n"
            "[Unsafe](javascript:alert(1))\n\n"
            "[Jump within](#next-steps)\n\n"
            "[Jump across](../decisions/storage.md#trade-offs)\n\n" +
            "Filler paragraph to make the target scroll.\n\n" * 30 +
            "## Next steps\n\nFindable final section.\n\n"
            "## Next steps\n\nDuplicate heading.\n\n"
            "Sources: codex:" + "x" * 150)
    nested = ("# Nested example\n\n1. Outer\n   - Inner\n\n     ```text\n"
              "     Sources: nested literal\n\n\n"
              "     Related: nested literal\n     ```\n\n"
              "\t- Safe text\n\nSources: codex:actual")
    data = {"root": "/synthetic/" + "long-notebook-name" * 12,
            "as_of": "2026-09-17T10:00:00Z", "categories": ["people", "projects", "decisions"],
            "records": [
                {"path": "projects/nested.md", "category": "projects", "title": "Nested example",
                 "text": nested, "updated": "2026-09-17"},
                {"path": "projects/layout.md", "category": "projects", "title": "Layout fixture",
                 "text": text, "updated": "2026-09-17"},
                {"path": "decisions/storage.md", "category": "decisions", "title": "Storage",
                 "text": "# Storage\n\n## Context\n\n" + "Context paragraph.\n\n" * 35 +
                         "## Trade-offs\n\nPortable Markdown.\n\n" + "Tail paragraph.\n\n" * 15,
                 "updated": "2026-09-17"}],
            "status": {"state": "Ready"}, "subscriptions": {},
            "logs": [{"started_at": "2026-09-17T10:00:00Z", "outcome": "completed",
                      "items": 12, "changed": [], "usage": {"input_tokens": 125000}, "seconds": 123}]}
    path = tmp_path / "reader.html"
    path.write_text(TEMPLATE.read_text().replace(PLACEHOLDER, json.dumps(data).replace("<", "\\u003c"), 1))
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url)
                if request.url.startswith(("http:", "https:")) else None)
        page.route("http://**/*", lambda route: route.abort())
        page.route("https://**/*", lambda route: route.abort())
        page.goto(path.as_uri() + "#r=projects%2Flayout.md")
        page.get_by_role("heading", name="Layout fixture", exact=True).wait_for()
        yield page, literal, diagram
        browser.close()
        assert not errors, errors
        assert not requests, requests


def test_reader_preserves_code_and_nested_lists(reader_page):
    page, literal, diagram = reader_page
    assert page.locator("pre").all_text_contents() == [
        literal, "def hello():\n    return '<safe>'", "```\nSources: still code", diagram]
    assert page.locator(".aside").inner_text().count("literal") == 0
    assert page.locator(".note > ol > li").count() == 2
    assert page.locator(".note > ol > li > ul > li").all_text_contents() == [
        "Check permissions", "Inspect history", "Record evidence", "Link decisions"]
    assert page.evaluate("window.wikiInjected === undefined")
    assert page.locator('.note a[href^="javascript:"]').count() == 0
    assert page.locator(".note script, .note img").count() == 0


@pytest.mark.parametrize("width,height", [(375, 812), (768, 1024), (1440, 1000)])
def test_reader_contains_overflow_and_keeps_content_visible(reader_page, tmp_path, width, height):
    page, _, _ = reader_page
    page.set_viewport_size({"width": width, "height": height})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.locator("#main").evaluate("e => e.getBoundingClientRect().top") < 260
    # Wide diagrams/tables scroll locally; inline tokens and sources wrap.
    assert page.locator("pre").last.evaluate("e => e.scrollWidth > e.clientWidth")
    assert page.locator(".table-scroll").evaluate("e => e.scrollWidth >= e.clientWidth")
    for selector in ["pre", ".table-scroll", ".chip"]:
        for node in page.locator(selector).all():
            assert node.evaluate("e => e.getBoundingClientRect().right <= innerWidth + 1")
    shots = Path(os.environ.get("CO_WIKI_SHOTS", str(tmp_path / "shots")))
    shots.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(shots / f"reader-{width}.png"), full_page=True)
    page.locator(".brand").click()
    page.get_by_role("heading", name="What your assistant knows").wait_for()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(shots / f"contents-{width}.png"), full_page=True)
    page.emulate_media(color_scheme="dark")
    page.screenshot(path=str(shots / f"contents-dark-{width}.png"), full_page=True)


def test_reader_mobile_menu_keyboard_and_resize(reader_page):
    from patchright.sync_api import expect

    page, _, _ = reader_page
    page.set_viewport_size({"width": 375, "height": 812})
    button = page.get_by_role("button", name="Browse notebook")
    expect(button).to_have_attribute("aria-expanded", "false")
    expect(page.locator("#nav")).not_to_be_visible()
    button.focus()
    page.keyboard.press("Enter")
    expect(button).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("Tab")
    expect(page.locator("#nav a").first).to_be_focused()
    page.keyboard.press("Escape")
    expect(button).to_have_attribute("aria-expanded", "false")
    expect(button).to_be_focused()
    page.keyboard.press("Space")
    page.locator("#nav").get_by_role("link", name="People").click()
    expect(page.get_by_role("heading", name="People", exact=True)).to_be_visible()
    expect(button).to_have_attribute("aria-expanded", "false")
    assert "No people mapped yet" in page.locator("#main").inner_text()
    assert page.locator("#main").evaluate("e => e.getBoundingClientRect().top") < 260
    page.set_viewport_size({"width": 1440, "height": 1000})
    expect(page.locator("#nav")).to_be_visible()
    expect(button).not_to_be_visible()
    page.set_viewport_size({"width": 768, "height": 1024})
    expect(page.locator("#nav")).not_to_be_visible()


def test_reader_heading_links_and_search_state(reader_page):
    from patchright.sync_api import expect

    page, _, _ = reader_page
    page.get_by_role("link", name="Jump within").click()
    page.wait_for_function("location.hash.includes('h=next-steps') && scrollY > 0")
    assert page.locator("#next-steps").evaluate("e => e.getBoundingClientRect().top >= 0 && e.getBoundingClientRect().top < innerHeight")
    assert page.locator("#next-steps-1").count() == 1
    page.get_by_role("link", name="Jump across").click()
    page.wait_for_function("location.hash.includes('h=trade-offs') && document.getElementById('trade-offs') && scrollY > 0")
    assert page.locator("#trade-offs").evaluate("e => e.getBoundingClientRect().top >= 0 && e.getBoundingClientRect().top < innerHeight")
    page.locator("#q").fill("portable")
    page.locator(".hits").get_by_role("link", name="Storage", exact=True).click()
    expect(page.get_by_role("heading", name="Storage", exact=True)).to_be_visible()
    expect(page.locator("#q")).to_have_value("")
    page.go_back()
    expect(page.locator("#q")).to_have_value("portable")
    expect(page.locator(".hits")).to_be_visible()


def test_reader_nested_fences_keep_literal_metadata(reader_page):
    page, _, _ = reader_page
    page.goto(page.url.split("#")[0] + "#r=projects%2Fnested.md")
    page.get_by_role("heading", name="Nested example", exact=True).wait_for()
    assert page.locator("pre").text_content() == "Sources: nested literal\n\n\nRelated: nested literal"
    assert "nested literal" not in page.locator(".aside").inner_text()
    assert "codex:actual" in page.locator(".aside").inner_text()
    # Unsupported tab-indented list syntax must not crash the whole reader.
    assert "Safe text" in page.locator(".note").inner_text()


def test_catalog_search_and_root_command_regressions(tmp_path):
    import json, shlex
    from patchright.sync_api import sync_playwright
    from connectonion.wiki.skill_map import map_skills
    root=tmp_path/"reader's notebook";prepare(root)
    source=tmp_path/'installed'
    for folder, description in [('one','Primary description'),('two','Unique alternative text')]:
        path=source/folder/'SKILL.md';path.parent.mkdir(parents=True)
        path.write_text(f'---\nname: Demo\ndescription: {description}\n---\n')
    map_skills(Notebook(root),[source]);path=write_reader(root)
    with sync_playwright() as api:
        browser=api.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page();page.goto(path.as_uri())
        assert 'Some are mapped skeletons' in page.locator('#main').inner_text()
        page.locator('#q').fill('Demo');page.wait_for_function("document.querySelectorAll('.hits > li').length === 1")
        assert page.locator('.hits > li').count()==1
        page.locator('#q').fill('Unique alternative');page.wait_for_timeout(300)
        page.locator('.hits .t a').click()
        page.locator('summary').click()
        assert page.locator('details a').count()==2
        page.locator('#nav a[href="#c=people"]').click()
        command=page.locator('#main .empty').inner_text().split('Run ',1)[1].split(' (or ',1)[0]
        assert shlex.split(command)==['co','wiki','--root',str(root),'init','--mail','outlook']
        browser.close()


def test_review_candidates_are_readable_and_inert(reader_page, tmp_path):
    page, _, _ = reader_page
    import json
    from connectonion.wiki.reader import TEMPLATE, PLACEHOLDER
    data = {"root": "/synthetic/owner's wiki", "as_of": "2026-09-20", "categories": [], "records": [],
            "reviews": [{"id": "abc123", "kind": "link", "subjects": ["projects/layout.md", "decisions/storage.md"],
                         "question": "Do these constraints share a cause?", "basis": "Two sourced decisions; connection remains unverified.", "status": "pending"},
                        {"id": "def456", "kind": "question", "subjects": ["projects/layout.md"],
                         "question": "<img src=x onerror=alert(1)>", "basis": "A literal quoted question", "status": "answered", "author": "User", "response": "Different scope"}]}
    path = tmp_path / "reviews.html"
    path.write_text(TEMPLATE.read_text().replace(PLACEHOLDER, json.dumps(data).replace("<", "\\u003c")))
    page.goto(path.as_uri() + "#reviews=1")
    page.get_by_role('heading', name='Questions & connections', exact=True).wait_for()
    assert page.locator('#main img').count() == 0
    command = page.locator('#main code').first.inner_text()
    import shlex
    assert shlex.split(command)[3] == "/synthetic/owner's wiki"
    assert '--verdict yes' in command
    shots = Path(os.environ.get('CO_WIKI_SHOTS', '/tmp/wiki-review-shots'))
    shots.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(shots / 'reviews-desktop.png'), full_page=True)
    page.set_viewport_size({'width': 375, 'height': 812})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(shots / 'reviews-mobile.png'), full_page=True)
