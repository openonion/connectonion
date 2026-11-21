"""Small seams on record pages (opt in with CO_REM_BROWSER_TEST=1); invented notebook.

- A related-page card whose basis comes from an Insight line printed the writer's prefix ("Changed: …").
- The page foot printed the raw file path as its button text; it says what it does, the path is the tooltip.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1", reason="opt in with CO_REM_BROWSER_TEST=1")


@pytest.fixture
def page(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    from connectonion.rem.reader import render
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = tmp_path / "rem"
    prepare(root)
    nb = Notebook(root)
    nb.write("orgs/fernhill.md", "# Fernhill Labs\n## Insight\n- Changed: Fernhill now hosts the [Cove pilot](../projects/cove.md) on site. [1]\n\n"
             "## Sources\n- [1] gmail:f1 — 2026-02-03 — Fernhill\n")
    nb.write("projects/cove.md", "# Cove\n## What it is\n- Cove sells heat storage to farms. [1]\n\n## Sources\n- [1] gmail:c1 — 2026-01-10 — Cove\n")
    path = tmp_path / "reader.html"
    path.write_text(render(root, local=True), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="en-US")
        page.route("http*://**/*", lambda route: route.abort())
        yield page, path.as_uri()
        browser.close()


def test_a_related_card_shows_the_sentence_without_the_writers_prefix(page):
    page, uri = page
    page.goto(uri + "#r=projects%2Fcove.md")
    page.wait_for_timeout(1200)
    text = page.locator("main").inner_text()
    assert "Fernhill now hosts the Cove pilot" in text
    assert "Changed:" not in text


def test_the_page_foot_says_copy_the_file_path_and_keeps_the_path_as_its_tooltip(page):
    page, uri = page
    page.goto(uri + "#r=projects%2Fcove.md")
    button = page.locator(".page-foot .copy-path").first
    button.wait_for()
    assert button.inner_text().strip() == "Copy the file path"
    assert button.get_attribute("title") == "projects/cove.md"
    assert "projects/cove.md" not in page.locator(".page-foot").inner_text()
