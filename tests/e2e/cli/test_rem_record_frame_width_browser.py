"""Every record kind opens at one page-frame width (#3231): a skill page fell through to main's 1180px
default while org/project/people/decision/knowledge pages sit in an 800px frame. The reading column was
always ~720px; the visible mismatch was the frame. Invented notebook.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


def test_a_skill_page_opens_at_the_same_frame_width_as_an_org_page(tmp_path):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    from rem_reader_notebook import build
    build(tmp_path / "rem", datetime(2026, 11, 20, tzinfo=timezone.utc))
    html = rem_reader.render(tmp_path / "rem", local=True)
    path = tmp_path / "reader.html"
    path.write_text(html, encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="en-US")
        page.route("http*://**/*", lambda route: route.abort())
        frames = {}
        for kind, record in (("skill", "skills/catalog/weekly-brief.md"),
                             ("org", "orgs/fernhill-labs.md"), ("project", "projects/harbour.md")):
            page.goto(path.as_uri() + "#r=" + record.replace("/", "%2F"))
            main = page.locator("#main")
            main.wait_for()
            box = main.bounding_box()
            frames[kind] = (round(box["x"]), round(box["width"]))
        # Every record page (skill, org, project) now shares the unified 3-column reading frame (#3306, #3231)
        # — identical left edge and identical 1128px width at 1440px, with >=660px middle prose + sticky page-nav.
        assert frames["skill"] == frames["org"] == frames["project"], frames
        assert 1080 <= frames["skill"][1] <= 1140, frames
        browser.close()
