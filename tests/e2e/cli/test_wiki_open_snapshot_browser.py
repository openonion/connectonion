"""The page `co wiki open` prints loads in a real browser (#1828).

`co wiki open` once printed chat.openonion.ai/<address>/wiki, a route O Chat did
not serve, and every test passed: they checked the string the CLI printed, never
whether a browser could show it. This one runs the default command on a tmp
notebook, opens the file:// page it names in headless Chrome, and uses it the
way a reader would. It skips, saying why, where no browser can be launched.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook


def _chrome(api):
    """Installed Chrome first (what the reader is opened in), then the bundled Chromium."""
    for channel in ("chrome", None):
        try:
            return api.chromium.launch(channel=channel, headless=True) if channel else \
                api.chromium.launch(headless=True)
        except Exception as error:  # not installed here: try the next, then skip
            reason = f"{type(error).__name__}: {str(error).splitlines()[0]}"
    pytest.skip(f"no Chrome or Chromium can be launched here ({reason})")


def _sync_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        try:
            from patchright.sync_api import sync_playwright
        except ImportError:
            pytest.skip("neither playwright nor patchright is installed")
    return sync_playwright


def test_default_open_page_loads_navigates_and_goes_back(tmp_path, monkeypatch):
    sync_playwright = _sync_playwright()
    monkeypatch.setattr("connectonion.wiki.service.mail_available", lambda kind: False)
    root = tmp_path / "wiki"
    prepare(root)
    Notebook(root).write("people/alice.md", "# Alice\n\nWorks on Project Aurora.\n")
    Notebook(root).write("projects/aurora.md", "# Aurora\n\nA synthetic project.\n")

    result = CliRunner().invoke(app, ["wiki", "--root", str(root), "--json", "open", "--no-launch"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert data["link"].startswith("file://") and Path(data["page"]).is_file()

    errors, console = [], []
    with sync_playwright() as api:
        browser = _chrome(api)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda msg: console.append(msg.text) if msg.type == "error" else None)
            page.route("http://**/*", lambda route: route.abort())
            page.route("https://**/*", lambda route: route.abort())
            page.goto(data["link"])
            contents = page.get_by_role("heading", name="What your assistant knows")
            contents.wait_for()
            page.locator("a[href='#c=people']").first.click()
            page.get_by_role("heading", name="People", exact=True).wait_for()
            assert page.evaluate("location.hash") == "#c=people"
            assert "Alice" in page.locator("#main").inner_text()
            page.go_back()
            contents.wait_for()
            assert not errors, errors
            assert not console, console
        finally:
            browser.close()


def test_a_mapped_page_leads_with_what_is_known(tmp_path, monkeypatch):
    """A page the mapper just built is mostly "Unknown — not investigated yet".
    The reader once printed every one of those lines, so each page opened on
    what the assistant does not know (#1836). Known facts come first; the
    empty headings are named once, with the command that fills them."""
    sync_playwright = _sync_playwright()
    monkeypatch.setattr("connectonion.wiki.service.mail_available", lambda kind: False)
    root = tmp_path / "wiki"
    prepare(root)
    notebook = Notebook(root)
    notebook.stub_person("people/quiet.md", "Quiet Person", handles=["quiet@example.com"])
    notebook.write("people/known.md", "# Known Person\n\nRuns the Aurora pilot with us.\n\n"
                   "## History\n- Observed mail count: 3; first: 2026-09-01; last: 2026-09-20.\n")

    result = CliRunner().invoke(app, ["wiki", "--root", str(root), "--json", "open", "--no-launch"])
    link = json.loads(result.stdout)["data"]["link"]
    with sync_playwright() as api:
        browser = _chrome(api)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(link + "#r=people/quiet.md")
            page.get_by_role("heading", name="Quiet Person").wait_for()
            text = page.locator("#main").inner_text()
            assert "Unknown" not in text
            assert "Mapped" in text
            assert "Not investigated yet: Who they are" in text
            assert "co wiki investigate 'people/quiet.md'" in text

            page.goto(link + "#c=people")
            page.get_by_role("heading", name="People", exact=True).wait_for()
            titles = page.locator(".hits .t a").all_inner_texts()
            assert titles.index("Known Person") < titles.index("Quiet Person")
            assert "Runs the Aurora pilot with us." in page.locator(".hits").inner_text()
        finally:
            browser.close()
