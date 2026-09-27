"""1.8.9b15's capture: a mapped page in the wiki reader (#1836).

The owner's own notebook cannot be shown -- it is their contacts -- so this
builds a synthetic one with the real code: `stub_person` writes the page the
mapper writes, `co wiki open --no-launch` renders the real reader, and
headless Chrome photographs it. Run from the repo root:

    python scripts/capture_189b15_release_reader.py docs/releases/assets/v1.8.9b15
"""
import json
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
root = Path(tempfile.mkdtemp()) / "wiki"
prepare(root)
notebook = Notebook(root)
notebook.stub_person("people/sam-lee.md", "Sam Lee", handles=["sam@example.com"])
notebook.write("people/mia-chen.md", "# Mia Chen\n\nRuns the Aurora pilot with us.\n\n"
               "## History\n- Observed mail count: 42; first: 2026-06-02; last: 2026-09-24.\n")

result = CliRunner().invoke(app, ["wiki", "--root", str(root), "--json", "open", "--no-launch"])
link = json.loads(result.stdout)["data"]["link"]
with sync_playwright() as api:
    browser = api.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800}, color_scheme="light")
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(link + "#r=people/sam-lee.md")
    page.get_by_role("heading", name="Sam Lee").wait_for()
    page.screenshot(path=str(out / "wiki-mapped-page.png"))
    browser.close()
print(out / "wiki-mapped-page.png")
