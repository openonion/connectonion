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
