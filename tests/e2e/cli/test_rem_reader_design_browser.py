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
         "#r=skills%2Fcatalog%2Fweekly-brief.md", "#q=pilot", "#q=mara", "#r=people%2Favery-lin.md", "#c=opportunities", "#reviews=1"]


@pytest.fixture
def reader(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    path = tmp_path / "reader.html"
    # Freeze the invented notebook so an age near a timezone day boundary is stable.
    frozen = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    snapshot = rem_reader.snapshot

    def fixed_snapshot(root):
        data = snapshot(root)
        data["as_of"] = frozen.isoformat()
        return data

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    path.write_text(rem_reader.render(build(tmp_path / "rem", frozen)), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url) if request.url.startswith("http") else None)
        page.route("http*://**/*", lambda route: route.abort())
        page.goto(path.as_uri())
        page.get_by_role("heading", name="What REM carried forward").wait_for()
        yield page, path.as_uri()
        browser.close()
        assert not errors, errors
        assert not requests, requests


def test_home_opens_on_what_to_remember_and_what_is_owed(reader):
    page, _ = reader
    memories = page.locator(".memory-card")
    assert memories.count() >= 3
    assert "Mara Ostrowski" in memories.all_inner_texts()[0]
    assert "pilot" in " ".join(memories.all_inner_texts()).lower()
    assert page.locator(".memory-connection a").count() >= 2
    recall = page.locator(".recall")
    assert recall.count() == 1
    assert not recall.locator(".recall-answer").is_visible()
    recall.get_by_role("button", name="Reveal the context").focus()
    page.keyboard.press("Enter")
    assert recall.locator(".recall-answer").is_visible()
    assert recall.get_by_role("button", name="Hide the context").get_attribute("aria-expanded") == "true"
    assert recall.get_by_role("button", name="Hide the context").get_attribute("aria-controls") == "recall-answer"
    assert page.locator(".night-details").count() == 1
    page.locator(".night-details summary").click()
    night = page.locator(".night")
    assert "46 items" in night.inner_text() and "4 pages" in night.inner_text()
    assert night.locator(".hypno .dot.woke").count() == 1  # the night that stopped early
    assert set(night.locator(".changes a").all_inner_texts()) == {"Mara Ostrowski", "Harbour", "Fernhill Labs", "Avery Lin"}  # runs, and stamps of the night
    # Yours first, then what others owe you.
    directions = [d.upper() for d in page.locator("ul.threads .dir").all_inner_texts()]
    assert directions[0] == "YOU OWE" and "THEY OWE" in directions
    assert directions == sorted(directions, key=["YOU OWE", "THEY OWE", "OPEN"].index)


def test_people_open_as_a_sheet_that_sorts_filters_and_opens_a_row(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#c=people")
    sheet = page.locator("table.sheet")
    assert sheet.locator("tbody tr").count() == 6
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


def test_the_people_sheet_fits_1440_and_says_when_it_is_cut(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#c=people")
    scroller = page.locator(".sheet-scroll")
    # Every column is visible at 1440, What's open included; nothing waits to the right.
    assert scroller.evaluate("e => e.scrollWidth <= e.clientWidth + 1")
    assert page.locator("th.c-open").evaluate("e => e.getBoundingClientRect().right <= innerWidth")
    assert "clip-right" not in page.locator(".sheet-box").get_attribute("class")
    # Narrower, the sheet scrolls inside itself, the cut edge shades, the name stays put.
    page.set_viewport_size({"width": 900, "height": 900})
    page.wait_for_function("document.querySelector('.sheet-box').classList.contains('clip-right')")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    scroller.evaluate("e => { e.scrollLeft = e.scrollWidth; }")
    page.wait_for_function("!document.querySelector('.sheet-box').classList.contains('clip-right')")
    assert page.locator("td.name").first.evaluate("e => e.getBoundingClientRect().left") >= scroller.evaluate("e => e.getBoundingClientRect().left") - 1


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


def test_pages_about_the_user_read_as_you_and_the_markdown_keeps_its_words(reader):
    page, _ = reader
    cases = {
        "The user has not signed it; with the user since 2026-09-22.": "You have not signed it; with you since 2026-09-22.",
        "the user's main contact": "your main contact",
        "Richard owes the user its P115 proposal": "Richard owes you its P115 proposal",
        "How the user writes to them": "How you write to them",
        "the user still owes Mara an answer": "you still owe Mara an answer",
        "the user is waiting; the user doesn't know": "you are waiting; you don't know",
        "the user should send a proposal": "you should send a proposal",
        "the user replies within a day": "you reply within a day",
    }
    assert page.evaluate("cases => Object.keys(cases).map(youify)", cases, isolated_context=False) == list(cases.values())
    # A thread addressed to the owner by name ("Avery: collect …") is the owner's to do.
    assert page.evaluate("direction('Avery: collect the swipe card from Security')", isolated_context=False) == "mine"
    home_threads = page.locator("ul.threads").first.inner_text()
    assert "you have owed them" in home_threads and "the user" not in home_threads.lower()
    page.goto(page.url.split("#")[0] + "#r=people%2Fmara-ostrowski.md")
    main = page.locator("#main").inner_text()
    assert "the user" not in main.lower() and "you have not signed it" in main
    assert page.get_by_role("heading", name="How you write to them").count() == 1
    assert page.evaluate("REM.records.find(r => r.path === 'people/mara-ostrowski.md').text.includes('the user has not signed it')", isolated_context=False)


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
