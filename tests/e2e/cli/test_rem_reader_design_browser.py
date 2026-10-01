"""The redesigned reader on a realistic notebook, in a real browser (opt in).

The fixture (tests/fixtures/rem_reader_notebook.py) is invented but shaped like
real pages: cited leads, Contact fields, open threads in both directions, a
dated History, numbered Sources, an ASCII Overview, a skill's usage, a week of
run logs. Each view is checked for what a returning reader came for, and every
view must fit a phone without sideways scrolling, in both themes.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)

VIEWS = ["", "#c=people", "#c=orgs", "#c=projects", "#c=skills", "#r=people%2Fmara-ostrowski.md",
         "#r=people%2Fquinn-alder.md", "#r=projects%2Fharbour.md", "#r=orgs%2Ffernhill-labs.md",
         "#r=skills%2Fcatalog%2Fweekly-brief.md", "#q=pilot", "#c=opportunities", "#reviews=1"]


@pytest.fixture
def reader(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem.reader import render
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    path = tmp_path / "reader.html"
    path.write_text(render(build(tmp_path / "rem", datetime.now(timezone.utc))), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url) if request.url.startswith("http") else None)
        page.route("http*://**/*", lambda route: route.abort())
        page.goto(path.as_uri())
        page.get_by_role("heading", name="What your assistant knows").wait_for()
        yield page, path.as_uri()
        browser.close()
        assert not errors, errors
        assert not requests, requests


def test_home_opens_on_the_night_and_what_is_owed(reader):
    page, _ = reader
    night = page.locator(".night")
    assert "46 items" in night.inner_text() and "3 pages" in night.inner_text()
    assert night.locator(".hypno .dot.woke").count() == 1  # the night that stopped early
    assert set(night.locator(".changes a").all_inner_texts()) == {"Mara Ostrowski", "Harbour", "Fernhill Labs"}
    # Yours first, then what others owe you.
    directions = [d.upper() for d in page.locator("ul.threads .dir").all_inner_texts()]
    assert directions[0] == "YOU OWE" and "THEY OWE" in directions
    assert directions == sorted(directions, key=["YOU OWE", "THEY OWE", "OPEN"].index)


def test_people_open_as_a_sheet_that_sorts_filters_and_opens_a_row(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#c=people")
    sheet = page.locator("table.sheet")
    assert sheet.locator("tbody tr").count() == 5
    assert "mara@fernhill.example" in sheet.inner_text()
    page.get_by_role("button", name="Yours to answer").click()
    assert sheet.locator("tbody .name a").all_inner_texts() == ["Mara Ostrowski", "Inès Halvorsen"]
    page.get_by_role("button", name="All").click()
    page.locator("th", has_text="Mails").locator("button").click()
    assert sheet.locator("tbody .name a").first.inner_text() == "Mara Ostrowski"
    assert page.locator("th", has_text="Mails").get_attribute("aria-sort") == "descending"
    page.locator(".sheet-find").fill("ledgerline")
    assert sheet.locator("tbody .name a").all_inner_texts() == ["Inès Halvorsen"]
    sheet.locator("tbody tr").first.locator("td").nth(5).click()
    page.get_by_role("heading", name="Inès Halvorsen", exact=True).wait_for()


def test_a_person_opens_on_a_fact_card_with_cited_values(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#r=people%2Fmara-ostrowski.md")
    # Under the title: what you owe and for how long.
    lead = page.locator(".leadrow .lead-open")
    assert lead.locator(".dir").inner_text().upper() == "YOU OWE" and lead.locator(".age").inner_text() == "9 days"
    card = page.locator(".factlist")
    value = lambda label: card.locator(f"dt:text-is('{label}') + dd")  # noqa: E731
    assert "Head of Partnerships" in value("Role").inner_text()
    assert value("Phone").get_attribute("class") == "none" and "not found" in value("Phone").inner_text()
    assert "title and company in signature" in value("Role").locator(".cite").get_attribute("data-tip")
    assert value("Email").locator(".qual").all_inner_texts() == ["work", "personal"]
    assert [b.upper() for b in page.locator(".insight .badge").all_inner_texts()] == ["NOW", "AT STAKE", "CHANGED", "PATTERN"]
    assert page.locator(".insight .cite.run").count() == 1  # [4][5][6] read as "3 sources"
    assert page.locator(".block-threads .thread.mine").count() == 1
    assert page.locator(".timeline li").count() == 5
    assert page.locator("#src-6").count() == 1


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_view_fits_a_phone(reader, theme):
    page, uri = reader
    page.emulate_media(color_scheme=theme)
    page.set_viewport_size({"width": 390, "height": 844})
    for view in VIEWS:
        page.goto(uri + (view or "#"))
        page.wait_for_timeout(120)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), view
        background = page.evaluate("getComputedStyle(document.body).backgroundColor")
        assert (background == "rgb(13, 16, 26)") == (theme == "dark"), (view, background)
