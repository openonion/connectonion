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
         "#r=skills%2Fcatalog%2Fweekly-brief.md", "#q=pilot", "#q=mara", "#r=people%2Favery-lin.md", "#c=opportunities", "#reviews=1",
         "#view=activity"]


def test_private_mapped_project_explains_why_it_waits_on_desktop_and_phone(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    from connectonion.rem.reader import render

    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).stub_project("projects/journal.md", "Journal", ["/work/journal"])
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    path = tmp_path / "reader.html"
    path.write_text(render(root))
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        for width in (1440, 375):
            page = browser.new_page(viewport={"width": width, "height": 812})
            page.goto(path.as_uri() + "#r=projects%2Fjournal.md")
            statement = page.locator(".focus-statement").inner_text()
            assert "Automatic investigations skip this private project." in statement
            assert "Name this page to request a write." in statement
            assert "clamped" not in page.locator(".focus-statement").get_attribute("class")
            assert "/work/journal" not in statement
            assert "Needs your explicit request" in page.locator(".focus-kicker").inner_text()
            assert "Automatic investigation skips this private project." in page.locator(".missing").inner_text()
            assert "investigate 'projects/journal.md'" in page.locator(".missing .cmd").inner_text()
            assert page.get_by_role("button", name="Copy the command").is_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.close()
        browser.close()


def test_mapped_project_hero_says_it_waits_instead_of_showing_its_folder(tmp_path, monkeypatch):
    """#2349: LayeredVisions, the busiest project, had not been written yet,
    and its hero read "WHERE THE WORK STANDS /Users/.../LayeredVisions"."""
    from patchright.sync_api import sync_playwright
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    from connectonion.rem.reader import render

    root = tmp_path / "rem"
    prepare(root)
    notebook = Notebook(root)
    notebook.stub_project("projects/browser.md", "browser", ["/work/browser"])
    page_text = notebook.read("projects/browser.md").replace(
        "- /work/browser", "- /work/browser\n- Sessions: 13\n- First seen: 2026-08-01\n- Last seen: 2026-08-02")
    notebook.write("projects/browser.md", page_text)
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    path = tmp_path / "reader.html"
    path.write_text(render(root))
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        for width in (1440, 375):
            page = browser.new_page(viewport={"width": width, "height": 812})
            page.goto(path.as_uri() + "#r=projects%2Fbrowser.md")
            statement = page.locator(".focus-statement").inner_text()
            assert "/work/browser" not in statement
            assert statement == "Not written yet: 13 sessions, last on 2026-08-02."
            assert "Where the work stands" not in page.locator(".focus-kicker").inner_text()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.close()
        browser.close()


def test_mobile_record_keeps_freshness_and_primary_navigation_in_reach(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    assert 'Snapshot ' in page.locator('#mobile-status').inner_text()
    assert 'Background updates off' in page.locator('#mobile-status').inner_text()
    assert 'Not started' not in page.locator('#mobile-status').inner_text()
    assert page.locator('#mobile-status').is_visible()
    for selector in ('#q', '.nav-toggle', '.mobile-back a'):
        assert page.locator(selector).bounding_box()['height'] >= 44
    assert page.get_by_role('heading', name='Full memory and sources').is_visible()
    assert page.locator('details.deep-note').get_attribute('open') is None
    page.locator('details.deep-note > summary').click()
    assert page.locator('.deep-note .note').is_visible()
    assert page.locator('.deep-note .note').bounding_box()['y'] < page.locator('.deep-note .side').bounding_box()['y']
    assert 'co\u00a0rem\u00a0start' in page.locator('#mobile-status').text_content()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.reload()
    assert 'Background updates off' in page.locator('#foot').inner_text()
    assert 'Not started' not in page.locator('#foot').inner_text()
    assert '`' not in page.locator('#foot').inner_text()


def test_mobile_browse_privacy_control_remains_a_full_touch_target(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.locator('.nav-toggle').click()
    privacy = page.get_by_role('button', name='Hide labelled passages')
    box = privacy.bounding_box()
    assert box['height'] >= 44 and box['width'] >= 44
    assert box['y'] >= 0 and box['y'] + box['height'] <= 812
    privacy.focus()
    privacy.press('Enter')
    shown = page.get_by_role('button', name='Show labelled passages')
    assert shown.get_attribute('aria-pressed') == 'true'
    assert shown.evaluate('(node) => node === document.activeElement')
    shown.press('Space')
    assert privacy.get_attribute('aria-pressed') == 'false'
    assert privacy.evaluate('(node) => node === document.activeElement')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


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

    def fixed_snapshot(root, local=False):
        data = snapshot(root, local)
        data["as_of"] = frozen.isoformat()
        return data

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    path.write_text(rem_reader.render(build(tmp_path / "rem", frozen), local=True), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url) if request.url.startswith("http") else None)
        page.route("http*://**/*", lambda route: route.abort())
        page.goto(path.as_uri())
        page.locator(".morning-primary h1").wait_for()
        yield page, path.as_uri()
        browser.close()
        assert not errors, errors
        assert not requests, requests


def test_home_opens_on_what_to_remember_and_what_is_owed(reader):
    page, _ = reader
    # One count everywhere: the heading says what "See all" and the sidebar say; the rows are the top three.
    total = page.locator('.waiting-more a').inner_text().split()[2]
    assert page.locator('.morning-primary h1').inner_text() == f'{total} things are waiting on you'
    assert page.locator('.waiting-ledger > li').count() == 3
    assert page.locator('.waiting-person a').all_inner_texts() == ['Mara Ostrowski', 'Inès Halvorsen', 'Fernhill Labs']
    assert 'Data-sharing addendum' in page.locator('.waiting-ask .words').first.inner_text()
    changes = page.locator('.overnight .claim-card')
    assert changes.count() == 1
    assert 'Head of Partnerships' in changes.inner_text()
    assert changes.get_by_role('link', name='Open the page and source →').get_attribute('href').endswith('h=src-2')
    assert set(page.locator('.week a').all_inner_texts()) >= {'Mara Ostrowski', 'Harbour', 'Fernhill Labs'}
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
    night = page.locator(".night-details .night")
    assert "46 items" in night.inner_text() and "4 pages" in night.inner_text()
    assert night.locator(".hypno .dot.changed").count() == 1
    assert night.locator('.hypno .dot.dawn').count() == 1
    assert set(night.locator(".changes a").all_inner_texts()) == {"Mara Ostrowski", "Harbour", "Fernhill Labs", "Avery Lin"}  # runs, and stamps of the night
    # The full ledger keeps both directions, yours first.
    page.locator('.waiting-more a').click()
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
    sheet.locator("th", has_text="Mails").locator("button").click()
    assert sheet.locator("tbody .name a").first.inner_text() == "Mara Ostrowski"
    assert sheet.locator("th", has_text="Mails").get_attribute("aria-sort") == "descending"
    page.locator(".sheet-find").fill("ledgerline")
    assert sheet.locator("tbody .name a").all_inner_texts() == ["Inès Halvorsen"]
    sheet.locator("tbody tr").first.locator("td").nth(5).click()
    page.get_by_role("heading", name="Inès Halvorsen", exact=True).wait_for()


def test_older_single_mail_contacts_are_findable_without_empty_memory_pages(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#c=people")
    page.locator(".contact-directory summary").click()
    directory = page.locator(".contact-directory")
    assert "3 other contacts" in directory.locator("summary").inner_text()
    assert "all available history" in directory.inner_text()
    directory.get_by_role("searchbox", name="Search other contacts").fill("Leah Bell")
    assert directory.locator("tbody tr").count() == 1
    assert "leah@old-friends.example" in directory.locator("tbody").inner_text()
    directory.get_by_role("button", name="Show the command to prepare a memory for Leah Bell").click()
    assert "stub person" in directory.locator(".directory-action code").inner_text()
    assert directory.locator("tbody tr").first.evaluate(
        "row => row.nextElementSibling.classList.contains('directory-action')")
    page.set_viewport_size({"width": 390, "height": 844})
    assert directory.locator("tbody tr").first.evaluate(
        "row => getComputedStyle(row).display === 'grid'")
    assert directory.get_by_role("button", name="Show the command to prepare a memory for Leah Bell").bounding_box()["height"] >= 44
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


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


def test_people_last_contact_heading_is_visible_beside_sticky_name_on_phone(reader):
    page, uri = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(uri + "#c=people")
    scroller = page.locator(".sheet-scroll")
    assert page.locator(".sheet th.c-last button").text_content().startswith("Last contact")
    assert any("· map" in date for date in page.locator(".sheet td.c-last").all_inner_texts())
    header_positions = """() => {
      const button = document.querySelector('.sheet th.c-last button');
      const firstLetter = document.createRange();
      firstLetter.setStart(button.firstChild, 0);
      firstLetter.setEnd(button.firstChild, 1);
      const letter = firstLetter.getBoundingClientRect();
      const name = document.querySelector('.sheet th.name').getBoundingClientRect();
      const edge = document.querySelector('.sheet-scroll').getBoundingClientRect();
      return { letterLeft: letter.left, nameLeft: name.left, nameRight: name.right,
        headingRight: button.getBoundingClientRect().right, edgeLeft: edge.left, edgeRight: edge.right };
    }"""
    for without_map_suffix in (False, True):
        if without_map_suffix:
            page.locator(".sheet td.c-last .mono").evaluate_all(
                "cells => cells.forEach(cell => cell.textContent = cell.textContent.replace(' · map', ''))")
        scroller.evaluate("e => { e.scrollLeft = e.scrollWidth; }")
        positions = page.evaluate(header_positions)
        assert positions["nameLeft"] >= positions["edgeLeft"] - 1, positions
        assert positions["letterLeft"] >= positions["nameRight"], positions
        assert positions["headingRight"] <= positions["edgeRight"], positions


def test_large_people_roster_keeps_mobile_controls_visible(reader, tmp_path, monkeypatch):
    from connectonion.rem import reader as rem_reader

    data = rem_reader.snapshot(tmp_path / "rem")
    example = next(r for r in data["records"] if r["title"] == "Quinn Alder")
    data["records"].extend({**example, "path": f"people/example-{i}.md",
                            "title": f"Alexandria Margaret Historical Correspondent {i:03d}"}
                           for i in range(570))
    monkeypatch.setattr(rem_reader, "snapshot", lambda _, local=False: data)
    path = tmp_path / "large-roster.html"
    path.write_text(rem_reader.render(tmp_path / "rem"), encoding="utf-8")

    page, _ = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(path.as_uri() + "#c=people")
    sheet = page.locator(".sheet-scroll")
    assert page.locator(".sheet tbody tr").count() >= 575
    directory = page.locator(".contact-directory summary")
    assert 0 <= directory.bounding_box()["y"] < 812
    assert directory.bounding_box()["y"] < sheet.bounding_box()["y"]
    directory.focus()
    directory.press("Enter")
    assert page.locator(".contact-directory").get_attribute("open") is not None
    page.locator(".contact-directory").get_by_role("searchbox", name="Search other contacts").fill("Leah Bell")
    assert page.locator(".contact-directory tbody tr").count() == 1
    for _ in range(2):
        sheet.evaluate("e => e.scrollLeft = e.scrollWidth")
        positions = page.evaluate("""() => {
          const button = document.querySelector('.sheet th.c-last button');
          const letter = document.createRange();
          letter.setStart(button.firstChild, 0);
          letter.setEnd(button.firstChild, 1);
          return { first: letter.getBoundingClientRect().left,
            name: document.querySelector('.sheet th.name').getBoundingClientRect().right,
            right: button.getBoundingClientRect().right,
            edge: document.querySelector('.sheet-scroll').getBoundingClientRect().right };
        }""")
        assert positions["first"] >= positions["name"], positions
        assert positions["right"] <= positions["edge"], positions
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert any("· map" in text for text in page.locator(".sheet td.c-last .mono").all_inner_texts())
        page.locator(".sheet th.c-last button").click()
        assert page.locator(".sheet th.c-last").get_attribute("aria-sort") in ("ascending", "descending")


def test_first_map_shows_results_next_step_and_held_count_on_phone(reader, tmp_path, monkeypatch):
    from connectonion.rem import reader as rem_reader

    data = rem_reader.snapshot(tmp_path / "rem")
    data["logs"] = []
    data["status"] = {"state": "Not started — run `co rem start` to begin"}
    for record in data["records"]:
        record["written"] = False
    next(r for r in data["records"] if r["title"] == "Quinn Alder")["needs_review"] = True
    for counts in data["counts"].values():
        counts["written"] = 0
    visible_people = sum(r["category"] == "people" and not r.get("needs_review") and not r.get("service")
                         for r in data["records"])
    monkeypatch.setattr(rem_reader, "snapshot", lambda _, local=False: data)
    path = tmp_path / "first-map.html"
    path.write_text(rem_reader.render(tmp_path / "rem"), encoding="utf-8")

    page, _ = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(path.as_uri())
    assert page.locator('.morning-primary h1').is_visible()
    assert page.locator('.first-map').is_visible()
    assert page.locator(".first-map h2").inner_text().endswith(" records mapped")
    assert page.locator(".first-map .morning-time").inner_text() == "0 memories written"
    assert page.locator(".first-map-actions a").inner_text() == f"Browse {visible_people} people →"
    assert page.locator(".first-map-actions a").is_visible()
    assert page.locator(".first-map-actions button").evaluate("e => e.getBoundingClientRect().bottom <= innerHeight")
    assert "Background updates off" in page.locator("#mobile-status").inner_text()
    page.locator(".first-map-actions a").click()
    assert "1 possible contact" in page.locator(".held-note").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_a_person_opens_on_the_relationship_ledger_with_facts_disclosed(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#r=people%2Fmara-ostrowski.md")
    assert page.locator('.person-lead').is_visible()
    assert 'Last contact' in page.locator('.contact-line').inner_text()
    assert page.locator('.ledger-column.mine h3 > span').first.inner_text() == 'You owe Mara'
    assert page.locator('.ledger-column.mine .ledger-count').inner_text() == '1'
    assert page.locator('.ledger-column.mine .ledger-meta').inner_text() == '9 days'
    assert page.locator('details.deep-note').get_attribute('open') is None
    assert not page.locator('.factlist').is_visible()
    page.locator('details.deep-note > summary').click()
    card = page.locator(".factlist")
    value = lambda label: card.locator(f"dt:text-is('{label}') + dd")  # noqa: E731
    assert "Head of Partnerships" in value("Role").inner_text()
    assert value("Phone").get_attribute("class") == "none" and "not found" in value("Phone").inner_text()
    role_source = value('Role').locator('.cite')
    assert role_source.inner_text() == 'Outlook, 22 Aug'
    assert role_source.get_attribute('aria-label') == 'Source: Outlook, 22 Aug, original not in this snapshot'
    assert 'title and company in signature' in page.locator('#src-2').inner_text()
    role_source.click()
    assert "The original isn't in this snapshot." in page.locator('#evidence-panel').inner_text()
    page.get_by_role('button', name='Close source context').click()
    assert role_source.evaluate('e => e === document.activeElement')
    assert value("Email").locator(".qual").all_inner_texts() == ["work", "personal"]
    assert [b.upper() for b in page.locator(".person-insight dt").all_inner_texts()] == ["NOW", "AT STAKE", "CHANGED", "PATTERN"]
    assert page.locator(".person-insight .cite.run").count() == 1  # [4][5][6] share one labelled chip
    assert page.locator(".ledger-column.mine .ledger-row").count() == 1
    assert page.locator(".deep-note .block-threads, .deep-note .block-insight").count() == 0
    assert page.locator(".timeline li").count() == 5
    assert page.locator("#src-6").count() == 1


def test_grouped_citation_sources_are_each_openable_on_phone(reader):
    page, uri = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    assert page.locator(".person-insight .cite.run").count() == 1
    page.goto(uri + "#r=people%2Fmara-ostrowski.md&h=src-6")
    assert page.locator("details.deep-note").get_attribute("open") is not None
    page.locator("#src-6 .source-open").click()
    assert "Source 1 of 1 for this line" in page.locator("#evidence-panel .evidence-top").inner_text()
    assert page.locator("#evidence-panel .evidence-original").is_visible()
    target = page.locator("#src-6 .source-open").bounding_box()
    assert target["height"] >= 44 and target["width"] >= 44
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


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
        # 1.9.2b1 pages: an adverb before the verb, and a compound adjective.
        "Use when the user explicitly asks": "Use when you explicitly ask",
        "a user-facing request; the user-facing copy": "a user-facing request; the user-facing copy",
    }
    assert page.evaluate("cases => Object.keys(cases).map(youify)", cases, isolated_context=False) == list(cases.values())
    # 1.9.2b1: these said nothing was open and showed as OPEN, "open for N days"; a real thread stays open.
    calm = ["None identified as of 2026-10-01.", "None as of 2026-09-30 [2].", "No explicit open request in the material.",
            "Nothing owed either way [3].", "No outstanding items.", "Nothing open as of 2026-10-02."]
    still_open = ["No reply from Lisa since 2026-09-12 [4].", "Unknown — whether Ody sent the invoice; Aaron asked 2026-09-30 [2]."]
    assert page.evaluate("t => t.map(isCalm)", calm + still_open, isolated_context=False) == [True] * 6 + [False] * 2
    # 1.9.2b1 skill pages: the finding after "Unknown — not verified." was hidden with the placeholder.
    record = {"path": "skills/catalog/x.md", "title": "x", "text": "# x\n\n## Current status\nUnknown — not verified. "
              "The latest session, 2026-06-09, proposed an npm CLI [1].\n\n## Limitations\nUnknown — not verified.\n"}
    kept = page.evaluate("r => known(r).kept.map(s => s.title)", record, isolated_context=False)
    assert kept == ["Current status"]
    # 1.9.2b1 History ranges: the end date leaked into the text or the gutter was blank.
    lines = "\n".join(["- 2026-08-26–2026-08-28: Town asked [1].", "- 2026-09-23 to 2026-10-09: Daily reports [2].",
                       "- 2026-08-10–11: Demos sent [3].", "- 2026-07-29–08-04: Trip [4].", "- 2025-10: Met at a meetup [5].", "- 2025-10–11: Term [6]."])
    got = page.evaluate("t => historyItems(t).map(i => [i.day, i.end, i.text.slice(0, 4)])", lines, isolated_context=False)
    assert got == [["2026-08-26", "2026-08-28", "Town"], ["2026-09-23", "2026-10-09", "Dail"],
                   ["2026-08-10", "2026-08-11", "Demo"], ["2026-07-29", "2026-08-04", "Trip"], ["2025-10", "", "Met "], ["2025-10", "2025-11", "Term"]]
    assert page.evaluate("dayLabel({day: '2025-10', end: ''})", isolated_context=False) == "Oct 2025"
    assert page.evaluate("dayLabel({day: '2026-08-10', end: '2026-08-11'})", isolated_context=False).count("–") == 1
    # A thread addressed to the owner by name ("Avery: collect …") is the owner's to do.
    assert page.evaluate("direction('Avery: collect the swipe card from Security')", isolated_context=False) == "mine"
    page.locator('.waiting-more a').click()
    home_threads = page.locator('.task-band .threads').first.inner_text()
    assert "you have owed them" in home_threads and "the user" not in home_threads.lower()
    page.goto(page.url.split("#")[0] + "#r=people%2Fmara-ostrowski.md")
    page.locator("details.deep-note > summary").click()
    main = page.locator("#main").inner_text()
    assert "the user" not in main.lower() and "you have not signed it" in main
    assert page.get_by_role("heading", name="How you write to them").count() == 1
    assert page.evaluate("REM.records.find(r => r.path === 'people/mara-ostrowski.md').text.includes('the user has not signed it')", isolated_context=False)


def test_a_compound_predicate_agrees_with_you_and_threads_name_the_right_debtor(reader):
    page, _ = reader
    # 1.9.2b1: "You run events there and has asked" — only the first verb agreed.
    cases = {
        "the user runs events there and has asked Mara for a deck": "you run events there and have asked Mara for a deck",
        "The user signed on 2026-09-02 but is waiting for the countersigned copy": "You signed on 2026-09-02 but are waiting for the countersigned copy",
        "the user sends invoices and receipts": "you send invoices and receipts",
        "Mara asked the user and has replied since": "Mara asked you and has replied since",
        "the user signed, and Tomas has asked for a copy": "you signed, and Tomas has asked for a copy",
    }
    assert page.evaluate("cases => Object.keys(cases).map(youify)", cases, isolated_context=False) == list(cases.values())
    # 1.9.2b1/b3 pages: who owes is the subject of the request, not the first name in the line.
    threads = {
        "User owes pickup of the replacement card at Gate 2 [1].": "mine",
        "Avery asked Mara on 2026-09-28 for a first reaction to the name; no reply [6].": "theirs",
        "Avery asked Tomas to arrange a call and provide a time [2].": "theirs",
        "Avery is awaiting Mara's answer to the 2026-08-19 question [10].": "theirs",
        "Mara asks Avery to choose a time for a 30-minute demo [8].": "mine",
        "Avery offered Mara a free two-week trial; acceptance is not shown [5].": "plain",
        "Avery offered to cover the $25 card fee [12].": "mine",
    }
    assert page.evaluate("t => t.map(direction)", list(threads), isolated_context=False) == list(threads.values())


def test_the_owner_focus_prefers_a_supported_change_to_a_generic_now(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Favery-lin.md")
    assert "Last active" in page.locator(".leadrow").inner_text()
    assert "Last contact" not in page.locator(".focus-facts").inner_text()
    assert "Wellington" in page.locator(".focus-facts").inner_text()
    selected = page.evaluate("""() => {
      const owner = REM.records.find(r => r.path === REM.owner);
      const insight = section(owner, 'insight');
      const original = insight.text;
      insight.text = '- Changed: Avery reversed the one-brief-per-person plan [2].\\n' + original;
      try {
        const focus = recordFocus(owner);
        return [memoryStatement(owner), focus.querySelector('.focus-next')?.textContent];
      } finally { insight.text = original; }
    }""", isolated_context=False)
    assert selected[0] == "Avery reversed the one-brief-per-person plan."
    assert "Next step" in selected[1] and "This month you shipped" in selected[1]
    assert "this month you shipped" in page.locator(".focus-statement").inner_text().lower()


def test_owner_next_step_keeps_its_source_and_private_label(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Favery-lin.md')
    page.evaluate("""() => {
      const owner = byPath(REM.owner);
      owner.text = owner.text.replace('## Insight\\n',
        '## Insight\\n- Changed: The brief plan changed [2].\\n- Now: Send the confidential draft [sensitive] [2].\\n');
      KNOWN.delete(owner.path); render();
    }""", isolated_context=False)
    step = page.locator('.focus-next')
    assert step.locator('.private').is_visible()
    assert step.locator('a.cite').count() == 1
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not step.locator('.private').is_visible()
    assert 'confidential draft' not in step.inner_text()


def test_focus_connects_project_people_org_and_archived_conversation(reader):
    page, uri = reader
    page.goto(uri + "#r=projects%2Fharbour.md")
    # This fixture names the pilot participants without linking their paths.
    # They remain available as text hints, behind progressive disclosure.
    page.locator('.mention-hints > summary').click()
    connected = page.locator(".related-records .relation-card")
    assert {name.strip() for name in connected.locator("strong").all_inner_texts()} >= {
        "Mara Ostrowski", "Fernhill Labs"}
    assert "what this project does" in page.locator('.focus-kicker').inner_text().lower()
    assert "command-line tool" in page.locator('.focus-statement').inner_text()
    assert "did not confirm current project work" in page.locator('.focus-limit').inner_text()
    assert page.get_by_role("heading", name="Recorded direction").is_visible()
    assert page.get_by_role("heading", name="Full memory and sources").is_visible()
    page.get_by_role("link", name="View all decisions").click()
    assert page.locator(".deep-note #key-decisions").is_visible()
    page.goto(uri + "#r=projects%2Fharbour.md")
    assert page.get_by_role("heading", name="Full memory and sources").is_visible()
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.locator("details.deep-note > summary").click()
    page.locator(".conversation-open").first.click()
    dialog = page.locator("#conversation-dialog")
    assert dialog.is_visible() and "usage export" in dialog.inner_text()
    dialog.get_by_role("button", name="Close conversation").click()
    assert page.locator(".conversation-open").first.evaluate("e => document.activeElement === e")
    page.locator("a.cite[href*='src-5']").first.click()
    evidence = page.locator("#evidence-panel")
    assert evidence.is_visible() and "I will send the usage export" in evidence.inner_text()


def test_conversations_precede_links_and_name_hints_keep_their_source_page(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r"""() => {
      const r = byPath('people/mara-ostrowski.md');
      REM.records.push({path: 'notes/run.md', category: 'notes', title: 'Run note', text: '# Run note'});
      r.relations = [
        {path: 'skills/catalog/weekly-brief.md', kind: 'linked', basis: 'Use the brief', via: r.path, sources: ['5']},
        {path: 'notes/run.md', kind: 'linked', basis: 'Run evidence', via: r.path, sources: []},
        {path: 'orgs/fernhill-labs.md', kind: 'mentioned by', basis: 'Mara in a directory',
         via: 'orgs/fernhill-labs.md', sources: ['1']}
      ];
      render();
    }""", isolated_context=False)
    page.locator('details.deep-note > summary').click()
    assert page.locator('.conversation-view').bounding_box()['y'] < page.locator('.related-records').bounding_box()['y']
    assert page.locator('.relation-card').filter(has_text='weekly-brief').is_visible()
    note = page.locator('.relation-card').filter(has_text='Run note')
    hint = page.locator('.relation-card').filter(has_text='Mara in a directory')
    assert not note.is_visible() and not hint.is_visible()
    page.locator('.notebook-links > summary').click()
    assert note.is_visible() and not hint.is_visible()
    page.locator('.mention-hints > summary').click()
    assert hint.is_visible()
    assert 'On Fernhill Labs' in hint.locator('..').inner_text()
    assert hint.locator('..').locator('a.cite').get_attribute('href') == '#r=orgs%2Ffernhill-labs.md&h=src-1'
    # Forward-link citations open the origin's original, not the destination's [5].
    page.locator('.related-records a.cite[href*="mara-ostrowski"]').first.click()
    assert 'I will send the usage export' in page.locator('#evidence-panel').inner_text()


def test_person_lead_shows_two_sentences_without_a_second_hero(reader):
    page, uri = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    text = "The user owes Mara a revised pilot agreement. She needs the usage export before Friday. A third sentence belongs in the full memory."
    page.evaluate("text => { const r = byPath('people/mara-ostrowski.md'); r.text = '# Mara Ostrowski\\n\\n' + text; KNOWN.clear(); FACTS.clear(); render(); }", text, isolated_context=False)
    assert page.locator('.person-lead').inner_text() == 'You owe Mara a revised pilot agreement. She needs the usage export before Friday.'
    assert page.locator('.focus-head, .contact-strip').count() == 0
    assert 'third sentence' not in page.locator('.person-lead').inner_text()
    page.locator('details.deep-note > summary').click()
    assert 'third sentence' in page.locator('.deep-note').inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_record_dates_do_not_disagree_when_the_index_is_stale(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    expected = page.evaluate("known(byPath('people/mara-ostrowski.md')).last", isolated_context=False)
    page.evaluate("() => { byPath('people/mara-ostrowski.md').index = {last_contact: '2001-01-01'}; FACTS.clear(); render(); }", isolated_context=False)
    formatted = page.evaluate('date => threadDate(date)', expected, isolated_context=False)
    # The quiet contact line and disclosed facts share the page date.
    assert formatted in page.locator('.lead-meta').inner_text()
    assert '2001' not in page.locator('.lead-meta').inner_text()
    page.locator('details.deep-note > summary').click()
    fact_date = page.evaluate('date => fmtDate(date)', expected, isolated_context=False)
    assert fact_date in page.locator('.factlist dt:text-is("Last contact") + dd').inner_text()


def test_empty_mail_keeps_private_header_evidence_without_inventing_a_body_excerpt(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      Object.assign(REM.source_context['outlook:77c09ad1e3f0'], {
        source: 'outlook', excerpt: '', body_empty: true, truncated: false, subject: 'Accepted: Workshop',
        participants: {from: 'mara@example.org', to: ['owner@example.org'], cc: []}
      });
    }""", isolated_context=False)
    page.locator('details.deep-note > summary').click()
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        trigger = page.locator('.deep-note a.cite[href$="h=src-5"]').first
        trigger.click()
        dialog = page.locator('#evidence-panel')
        assert 'The retained message has no body text. Its headers are available.' in dialog.inner_text()
        assert dialog.locator('.evidence-empty-body').is_visible()
        assert 'Accepted: Workshop' in dialog.locator('.evidence-subject').inner_text()
        assert not dialog.locator('blockquote').count()
        assert not dialog.locator('.evidence-unavailable').count()
        # A message (#2106): the sender and their address head it, recipients follow.
        assert 'mara@example.org' in dialog.locator('.msg-head').inner_text()
        assert dialog.locator('.evidence-participants .msg-person').count() == 1
        page.evaluate('togglePrivate()', isolated_context=False)
        assert not dialog.locator('.evidence-original').is_visible()
        assert not dialog.locator('.evidence-subject').is_visible()
        page.evaluate('togglePrivate()', isolated_context=False)
        assert dialog.locator('.evidence-empty-body').is_visible()
        page.get_by_role('button', name='Close source context').click()
        assert trigger.evaluate('e => e === document.activeElement')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_project_first_seen_does_not_establish_an_unknown_start_date(reader):
    page, uri = reader
    page.goto(uri + "#r=projects%2Fharbour.md")
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = r.text.replace('# Harbour', '# Harbour\\n\\n## Facts\\n- Started: Unknown');
      FACTS.clear(); render();
    }""", isolated_context=False)
    assert page.evaluate("facts(byPath('projects/harbour.md')).first", isolated_context=False)
    page.locator('details.deep-note > summary').click()
    started = page.locator('.factlist dt:text-is("Started") + dd')
    assert started.locator('.val').count() == 0
    assert 'not found' in started.inner_text()


def test_project_hero_leads_with_current_finding_before_historical_pattern(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Insight\\n- Pattern: Historical send rule: verified recipient, approved text, screenshot, no retries. [1]\\n'
        + '- Changed: A later UI request corrected its wording. [2]\\n- Now: A release was requested in July. [3]';
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    for width in (1440, 768, 375):
        page.set_viewport_size({'width': width, 'height': 1000})
        assert page.locator('.focus-statement').inner_text() == 'A release was requested in July.'


def test_unknown_repository_stays_unknown_while_workspace_path_remains_visible(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Facts\\n- Repository: Unknown\\n- Started: Unknown\\n'
        + '\\n## Insight\\n- At stake: Keep the source folder intact. [1]\\n'
        + '\\n## Paths\\n- /tmp/session-workspace\\n- Sessions: 4\\n- First seen: 2026-07-18\\n- Last seen: 2026-07-20';
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    assert page.locator('.focus-facts dt:text-is("Local path") + dd').inner_text() == '/tmp/session-workspace'
    assert not page.locator('.focus-facts dt:text-is("Repository")').count()
    page.locator('details.deep-note > summary').click()
    repository = page.locator('.factlist dt:text-is("Repository") + dd')
    assert not repository.locator('.val').count()
    assert 'not found' in repository.inner_text()
    page.evaluate("() => { location.hash = '#q=Harbour'; render(); }", isolated_context=False)
    assert page.locator('.best-facts dt:text-is("Local path") + dd').inner_text() == '/tmp/session-workspace'
    assert not page.locator('.best-facts dt:text-is("Repository")').count()


def test_investigation_command_targets_the_notebook_being_viewed(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fquinn-alder.md")
    root = page.evaluate('REM.root', isolated_context=False)
    command = page.locator('.missing .cmd code').inner_text()
    assert '--root' in command and root in command
    assert "investigate 'people/quinn-alder.md'" in command


def test_private_mode_hides_raw_sources_and_conversations_already_open(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    page.locator('details.deep-note:not([open]) > summary').click()
    page.locator('.conversation-open').first.click()
    messages = page.locator('#conversation-dialog .conversation-message')
    assert messages.first.is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not messages.first.is_visible()
    assert page.locator('#conversation-dialog .private-hidden-notice').is_visible()
    page.get_by_role('button', name='Close conversation').click()
    page.locator("a.cite[href*='src-5']").first.click()
    original = page.locator('#evidence-panel .evidence-original')
    assert original.count() == 1 and not original.is_visible()
    assert page.locator('#evidence-panel .private-hidden-notice').is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert original.is_visible() and 'I will send the usage export' in original.inner_text()


def test_private_project_summary_is_clear_on_desktop_and_phone(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Insight\\n- Now: A hidden finding [personal].\\n'
        + '\\n## What it is\\n- A hidden description [personal].\\n'
        + '\\n## Key decisions\\n- A hidden decision [personal].\\n'
        + '\\n## Sources\\n- [1] codex:example — 2026-09-01\\n'
        + '\\nInvestigation: mapped 2026-09-01 · investigated 2026-10-01 (codex)';
      r.project_coverage = {inputs_read: 3, inputs_available: 5, days: 150, scope: 'archived'};
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        assert page.locator('.scope-note').count() == 0
        assert 'clamped' not in page.locator('.focus-statement').get_attribute('class')
        page.evaluate('togglePrivate()', isolated_context=False)
        assert page.locator('.focus-statement').inner_text() == 'Hidden labelled passage'
        assert page.locator('.project-purpose-preview').inner_text() == 'Hidden labelled passage'
        assert page.locator('.project-workspace').get_by_text('Hidden labelled passage').count() == 1
        assert page.locator('.project-workspace').get_by_text('Hidden labelled passage').first.is_visible()
        page.evaluate("() => { location.hash = '#c=projects'; render(); }", isolated_context=False)
        row = page.locator('tr', has=page.get_by_role('link', name='Harbour'))
        cell = row.locator('td').nth(1)
        assert cell.inner_text() == 'Hidden labelled passage'
        assert cell.locator('.clamp').get_attribute('title') == ''
        if width == 375:
            assert row.locator('.mobile-status-label').inner_text() == 'Investigated'
            assert row.locator('.mobile-status-label').is_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.evaluate("() => { location.hash = '#r=projects%2Fharbour.md'; render(); }", isolated_context=False)
        page.evaluate('togglePrivate()', isolated_context=False)


def test_project_without_a_current_insight_leads_with_purpose_and_input_limit(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Insight\\n- Unknown\\n'
        + '\\n## What it is\\n- Harbour reads a local daily log. [1]\\n'
        + '\\n## Where it stands\\n- The checkout snapshot has a recent commit. [1]\\n'
        + '\\n## Sources\\n- [1] project-source:fixture — README snapshot\\n'
        + '\\nInvestigation: mapped 2026-09-01 · investigated 2026-10-01 (codex)';
      r.project_coverage = {inputs_read: 3, inputs_available: 5, days: 7, scope: 'archived'};
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        assert page.locator('.focus-kicker').first.inner_text() == 'What this project does'
        assert 'reads a local daily log' in page.locator('.focus-statement').inner_text()
        assert 'recent commit' not in page.locator('.focus-statement').inner_text()
        assert '7-day session sample did not confirm current project work' in page.locator('.focus-limit').inner_text()
        assert page.locator('.project-workspace').get_by_text('What this is').count() == 0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.evaluate("() => { byPath('projects/harbour.md').project_coverage.inputs_read = 0; render(); }",
                  isolated_context=False)
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        assert 'No coding-session input was assigned' in page.locator('.focus-limit').inner_text()
        assert page.locator('.scope-note').count() == 0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_written_project_purpose_and_source_fit_on_phone(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Insight\\n- Now: The user asked to organize a folder in August; whether the requested work was completed is unknown. [1]\\n'
        + '\\n## What it is\\nA property lead workflow to collect contacts and ask owners whether they permit short stays. [1]\\n'
        + '\\n## Key decisions\\n- Collect property details before filtering. [1]\\n'
        + '\\n## Sources\\n- [1] codex:example — 2026-08-02\\n'
        + '\\nInvestigation: mapped 2026-10-03 · investigated 2026-10-04 (codex)';
      r.project_coverage = {inputs_read: 114, inputs_available: 116, days: 90, scope: 'archived'};
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    purpose = page.locator('.project-purpose-preview')
    assert 'property lead workflow' in purpose.inner_text()
    assert purpose.bounding_box()['y'] < 812
    assert page.locator('.scope-note').count() == 0
    purpose_source = page.locator('.project-purpose-cites a.cite').first
    assert purpose_source.get_attribute('aria-label').startswith('Source: Session, 2 Aug')
    assert purpose_source.get_attribute('data-tip') is None
    sources = page.locator('.focus-source').bounding_box()
    assert sources['height'] >= 44 and sources['y'] + sources['height'] <= 812
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_long_project_purpose_keeps_a_source_in_the_phone_first_screen(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      const purpose = 'A shared-inbox tool for a team to review long threads, identify decisions and unresolved follow-ups, and prepare a weekly brief before a renewal call. '.repeat(2);
      r.text = r.text.replace(/## What it is\\n- [^\\n]+/, '## What it is\\n- ' + purpose + '[1].');
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    statement = page.locator('.focus-statement')
    assert statement.evaluate('(node) => node.scrollHeight > node.clientHeight')
    chip = page.locator('.project-purpose-cites a.cite').first
    source = page.locator('.focus-source')
    assert chip.bounding_box()['y'] + chip.bounding_box()['height'] <= 812
    assert source.bounding_box()['y'] + source.bounding_box()['height'] <= 812
    page.get_by_role('button', name='Read full purpose').click()
    assert not statement.evaluate('(node) => node.scrollHeight > node.clientHeight')
    assert 'weekly brief before a renewal call' in statement.inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_written_pages_show_the_complete_source_action_on_phone(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    paths = ('people/avery-lin.md', 'orgs/fernhill-labs.md',
             'people/mara-ostrowski.md', 'projects/harbour.md',
             'skills/catalog/weekly-brief.md')
    for path in paths:
        page.goto(uri + '#r=' + path.replace('/', '%2F'))
        if path == 'skills/catalog/weekly-brief.md':
            page.evaluate("""() => {
              const r = byPath('skills/catalog/weekly-brief.md');
              r.text = '# weekly-brief\\n\\n## Insight\\nA saved draft needs a queue readback before it can be sent. [1]\\n'
                + '\\n## When to use\\nUse for a weekly brief. [1]\\n'
                + '\\n## Sources\\n- [1] skill-record:test — saved draft and queue readback.';
              KNOWN.delete(r.path); render();
            }""", isolated_context=False)
        if path == 'people/mara-ostrowski.md':
            assert page.locator('details.deep-note').get_attribute('open') is None
            page.locator('details.deep-note > summary').click()
            page.goto(uri + '#r=people%2Fmara-ostrowski.md&h=sources')
            page.locator('.deep-note .block-sources').wait_for(state='visible')
            continue
        link = page.get_by_role('link', name='View sources →')
        assert link.count() == 1, path
        box = link.bounding_box()
        assert box['height'] >= 44 and box['y'] + box['height'] <= 812, path
        assert page.get_by_role('heading', name='Full memory and sources').is_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        link.click()
        page.locator('.deep-note .block-sources').wait_for(state='visible')


def test_open_context_is_not_counted_as_waiting_on_other_people(reader):
    page, _ = reader
    page.evaluate("() => { const r = byPath('people/mara-ostrowski.md'); r.text = r.text.replace('## Open threads\\n', '## Open threads\\n- Completion evidence not recorded.\\n'); KNOWN.clear(); render(); }", isolated_context=False)
    page.locator('.waiting-more a').click()
    others = page.locator('.task-band', has=page.get_by_role('heading', name='Waiting on others'))
    plain = page.locator('.task-band', has=page.get_by_role('heading', name='Other open context'))
    assert others.locator('.thread.theirs').count() > 0
    assert others.locator('.thread.plain').count() == 0
    assert 'Completion evidence not recorded' in plain.inner_text()


def test_changes_and_open_threads_are_actionable_destinations(reader):
    page, uri = reader
    page.goto(uri + "#view=changes")
    assert "Head of Partnerships" in page.locator(".claim-card").first.inner_text()
    page.locator(".claim-card a").first.click()
    page.get_by_role("heading", name="Mara Ostrowski", exact=True).wait_for()
    page.goto(uri + "#view=open")
    assert page.get_by_role("heading", name="Open threads").is_visible()
    assert page.locator(".task-band .thread").count() >= 2
    assert page.locator(".task-band a[href*='people']").count() >= 1


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
        assert (background == "rgb(14, 17, 32)") == (theme == "dark"), (view, background)


def test_source_and_conversation_show_input_limits_and_hide_them_with_private_content(reader):
    page, uri = reader
    scope = 'Codex Desktop voice transcription; only explicit input, transcript delta omitted; recognition errors possible'
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("scope => { const c = REM.source_context['outlook:77c09ad1e3f0']; c.input_scope = scope; REM.conversations[c.thread].messages[0].input_scope = scope; }", scope, isolated_context=False)
    page.locator("a.cite[href*='src-5']").first.click()
    note = page.locator('#evidence-panel .evidence-input-scope')
    assert note.is_visible() and 'Transcription may contain errors.' in note.inner_text() and 'transcript delta' not in note.inner_text()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not note.is_visible()
    page.get_by_role('button', name='Close source context').click()
    page.evaluate('togglePrivate()', isolated_context=False)
    page.locator('details.deep-note:not([open]) > summary').click()
    page.locator('.conversation-open').first.click()
    note = page.locator('#conversation-dialog .evidence-input-scope')
    assert note.is_visible() and 'Transcription may contain errors.' in note.inner_text() and 'transcript delta' not in note.inner_text()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not note.is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_recovered_mail_shows_participants_and_separate_archive_clock_privately(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      Object.assign(REM.source_context['outlook:77c09ad1e3f0'], {
        participants: {from: 'Mentor <mentor@example.org>', to: ['me@example.org'], cc: ['Guest <guest@example.org>']},
        captured_at: '', retained_at: '2026-10-01T10:00:00Z',
        body_format: 'provider-rendered text, not original MIME',
        excerpt: ('Mail body excerpt.' + String.fromCharCode(10)).repeat(30), truncated: true,
        input_scope: 'Historical citation recovery. Original retrieval time unknown; initial window unchanged.'
      });
    }""", isolated_context=False)
    cite = page.locator("a.cite[href*='src-5']").first
    cite.click()
    dialog = page.locator('#evidence-panel')
    participants = dialog.locator('.evidence-participants')
    assert participants.is_visible()
    head = dialog.locator('.msg-head').inner_text()
    assert 'Mentor' in head and 'mentor@example.org' in head
    assert 'Cc' in participants.inner_text() and 'Guest' in participants.inner_text()
    assert participants.locator('[title="guest@example.org"]').count() == 1
    assert 'Outlook' in dialog.locator('.msg-time').inner_text() and 'Archived ' in dialog.inner_text()
    assert 'Original retrieval time unknown' in dialog.inner_text()
    assert 'Retrieved ' not in dialog.inner_text()
    assert 'provider-rendered text, not original MIME' in dialog.inner_text()
    assert not participants.locator('mentor').count()
    for private in (True, False):
        page.evaluate('togglePrivate()', isolated_context=False)
        assert participants.is_visible() == (not private)
        assert dialog.locator('blockquote').is_visible() == (not private)
        assert dialog.locator('.evidence-input-scope').is_visible() == (not private)
    assert dialog.evaluate('e => e.scrollWidth <= e.clientWidth')
    dialog.locator('blockquote').scroll_into_view_if_needed()
    close = page.get_by_role('button', name='Close source context')
    box = close.bounding_box()
    assert box['height'] >= 44
    assert 0 <= box['y'] <= 812 - box['height']
    close.click()
    assert cite.evaluate('e => e === document.activeElement')


def test_native_conversation_shares_common_limits_and_keeps_voice_limits(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      const c = REM.conversations[REM.source_context['outlook:77c09ad1e3f0'].thread];
      const common = 'Your input only. Assistant replies and tool results are not included, so this does not verify what was completed.';
      c.messages = [{excerpt: 'Approve the design.', input_scope: common},
        {excerpt: 'Make the title shorter.', input_scope: common},
        {excerpt: 'Voice request.', input_scope: 'Codex Desktop voice transcription; recognition errors possible'}];
      c.total = 3;
    }""", isolated_context=False)
    page.locator('details.deep-note:not([open]) > summary').click()
    page.locator('.conversation-open').first.click()
    dialog = page.locator('#conversation-dialog')
    assert dialog.locator(':scope > .evidence-input-scope').count() == 1
    assert dialog.locator('.conversation-message .evidence-input-scope').count() == 1
    assert 'Transcription may contain errors.' in dialog.inner_text()
    assert 'Approve the design.' in dialog.inner_text()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not dialog.locator(':scope > .evidence-input-scope').is_visible()
    assert not dialog.locator('.conversation-message').first.is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_source_times_use_notebook_timezone_on_another_browser_timezone(reader):
    page, uri = reader
    other = page.context.browser.new_page(timezone_id='America/Los_Angeles', locale='en-US')
    other.goto(uri)
    other.evaluate("REM.status.timezone = 'Australia/Sydney'", isolated_context=False)
    assert 'Jul 31' in other.evaluate("fmtTime('2026-07-30T21:04:03Z')", isolated_context=False)
    assert 'Jul 30' in other.evaluate("new Date('2026-07-30T21:04:03Z').toLocaleDateString('en-US', {month:'short',day:'numeric'})")
    other.close()


def test_open_request_dates_keep_explicit_deadlines_on_the_notebook_calendar(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r"""() => {
      REM.status.timezone = 'Australia/Sydney'; REM.as_of = '2026-10-02T14:30:00Z';
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace(/## Open threads[\s\S]*?(?=\n## )/, '## Open threads' + String.fromCharCode(10) +
        '- You owe Mara a scope decision, requested 2026-10-01; due 2026-10-03 [5].' + String.fromCharCode(10));
      KNOWN.clear(); render();
    }""", isolated_context=False)
    row = page.locator('.ledger-column.mine .ledger-row').first
    assert row.locator('.ledger-meta').inner_text() == 'due 3 Oct'
    page.evaluate("REM.as_of = '2026-10-03T14:30:00Z'; render()", isolated_context=False)
    assert page.locator('.ledger-column.mine .ledger-meta').first.inner_text() == 'overdue · 3 Oct'
    dates = page.evaluate("threads(byPath('people/mara-ostrowski.md')).items[0]", isolated_context=False)
    assert dates['since'] == '2026-10-01' and dates['due'] == '2026-10-03'
    dates = page.evaluate(r"""() => {
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace('requested 2026-10-01; due 2026-10-03', 'requested 2026-10-01; meeting 2026-10-05');
      KNOWN.clear(); return threads(r).items[0];
    }""", isolated_context=False)
    assert dates['since'] == '2026-10-01' and dates['due'] == ''


def test_phone_open_preview_names_elapsed_age_and_keeps_the_full_thread(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r"""() => {
      REM.status.timezone = 'Australia/Sydney'; REM.as_of = '2026-10-03T14:30:00Z';
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace(/## Open threads[\s\S]*?(?=\n## )/, '## Open threads' + String.fromCharCode(10) +
        '- Mara asked Avery to confirm the scope on 2026-09-29, followed up twice, and offered several detailed ways to answer before a time-sensitive proposal, while the exact due day still needs confirmation [5].' + String.fromCharCode(10));
      KNOWN.clear(); render();
    }""", isolated_context=False)
    ledger = page.locator('.ledger-column.mine')
    assert ledger.locator('.ledger-meta').inner_text() == '5 days'
    assert 'exact due day still needs confirmation' in ledger.inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_dates_and_contact_age_use_notebook_calendar_on_another_browser_timezone(reader):
    page, uri = reader
    other = page.context.browser.new_page(timezone_id='America/Los_Angeles', locale='en-US')
    other.goto(uri + '#r=people%2Fmara-ostrowski.md')
    other.evaluate("""() => {
      REM.status.timezone = 'Australia/Sydney';
      REM.as_of = '2026-10-02T22:00:00Z';
      const r = REM.records.find(r => r.path === 'people/mara-ostrowski.md');
      r.last_activity = '2026-10-02';
      r.text = r.text.replace(/Last contact:[^\\n]+/g, 'Last contact: 2026-10-02 [1]');
      KNOWN.delete(r.path); FACTS.delete(r.path); render();
    }""", isolated_context=False)
    assert 'Last contact 2 Oct' in other.locator('.contact-line').inner_text()
    assert other.evaluate("fmtDate('2026-07-31T23:03:58Z')", isolated_context=False) == 'Aug 1, 2026'
    assert other.evaluate("fmtDate('2026-07-31')", isolated_context=False) == 'Jul 31, 2026'
    other.evaluate("REM.as_of = '2026-12-31T14:00:00Z'", isolated_context=False)
    assert other.evaluate("shortDate('2026-12-31')", isolated_context=False) == 'Dec 31, 2026'
    other.evaluate("REM.as_of = '2026-10-03T15:30:00Z'", isolated_context=False)
    assert other.evaluate("daysSince('2026-10-03')", isolated_context=False) == 1
    other.close()


def test_phone_activity_shows_complete_rows_with_latest_first(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      const r = REM.records.find(r => r.path === 'people/mara-ostrowski.md');
      const start = r.text.indexOf('## History'), end = r.text.indexOf('## ', start + 3);
      const rows = [2, 1, 4, 3].map(n => '- 2026-09-0' + n + ': ' + 'Confirmed the venue plan, with event completion unknown. '.repeat(5) + '[1]');
      r.text = r.text.slice(0, start) + '## History\\n' + rows.join('\\n') + '\\n' + r.text.slice(end);
      KNOWN.delete(r.path); render();
    }""", isolated_context=False)
    assert page.locator('.activity-day').all_inner_texts() == ['4 Sep', '3 Sep', '2 Sep', '1 Sep']
    assert page.locator('.activity-text').count() == 4
    assert all(text.count('Confirmed the venue plan') == 5 for text in page.locator('.activity-text').all_inner_texts())
    assert page.locator('.activity-list').evaluate('e => e.scrollHeight <= e.clientHeight')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_reviewed_role_and_unknown_company_override_older_index(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      const r = REM.records.find(r => r.path === 'people/mara-ostrowski.md');
      r.text = r.text.replace(/^- Role:[^\\n]+/m, '- Role: Programme manager (historical current unknown) [1]')
        .replace(/^- Company:[^\\n]+/m, '- Company: Unknown');
      r.index = {...r.index, role: 'Current CEO', company: 'Old employer'};
      KNOWN.delete(r.path); FACTS.delete(r.path); render();
    }""", isolated_context=False)
    assert 'Programme manager (historical current unknown)' in page.locator('.contact-line').inner_text()
    assert 'Old employer' not in page.locator('.contact-line').inner_text()
    page.evaluate("""() => {
      const r = REM.records.find(r => r.path === 'people/mara-ostrowski.md');
      r.text = r.text.replace(/^- Company:[^\\n]+\\n/m, '');
      KNOWN.delete(r.path); FACTS.delete(r.path); render();
    }""", isolated_context=False)
    assert 'Old employer' in page.locator('.contact-line').inner_text()


def test_instruction_excerpt_is_not_a_verified_result_and_respects_privacy(reader):
    page, uri = reader
    source = 'skill-source:' + 'a' * 16
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
    page.evaluate("""source => {
      const r = REM.records.find(r => r.path === 'skills/catalog/weekly-brief.md');
      r.text = '# weekly-brief\\n\\n## What it does\\nCheck the actual artifact. [1]\\n\\n## Insight\\nVerify the artifact before claiming success. [1]\\n\\n## Sources\\n- [1] ' + source;
      REM.source_context[source] = {source: 'skill-source', excerpt: 'Check the actual artifact before claiming success.',
        input_scope: 'Skill instructions; intended behavior, not verified execution. Recovered from a file whose content matches the citation hash.',
        truncated: false};
      KNOWN.delete(r.path);
      render();
    }""", source, isolated_context=False)
    page.locator('a.cite').first.click()
    dialog = page.locator('#evidence-panel')
    assert 'instruction excerpt' in dialog.inner_text().lower()
    assert 'not a verified result' in dialog.inner_text()
    assert 'recovered from matching file content' in dialog.inner_text()
    assert dialog.locator('blockquote').inner_text() == 'Check the actual artifact before claiming success.'
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not dialog.locator('blockquote').is_visible()
    assert not dialog.locator('.evidence-input-scope').is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert dialog.locator('blockquote').is_visible()
    page.get_by_role('button', name='Close source context').click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_long_skill_source_find_reaches_passages_and_keeps_original(reader):
    page, uri = reader
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
        page.evaluate("""() => {
          const r = byPath('skills/catalog/weekly-brief.md');
          const source = 'skill-record:' + 'b'.repeat(64);
          r.text = '# weekly-brief\\n\\n## Insight\\nA queue readback checked the saved draft. [1]'
            + '\\n\\n## Sources\\n- [1] ' + source;
          const part = ('{"step":"invented source"},\\n').repeat(650);
          REM.source_context[source] = {source: 'skill-record',
            excerpt: 'İstanbul\\n' + part + 'Queue readback checked the first draft.\\n' + part
              + 'Queue readback checked the second draft.\\n', truncated: true};
          KNOWN.delete(r.path);
          render();
        }""", isolated_context=False)
        cite = page.locator('a.cite').first
        cite.click()
        dialog = page.locator('#evidence-panel')
        find = dialog.get_by_role('searchbox', name='Find in archived source')
        assert find.is_visible()
        assert 'truncated' in dialog.inner_text().lower()
        original = dialog.locator('blockquote').inner_text()
        span = dialog.locator('.evidence-original mark.span').inner_text()
        assert span == 'Queue readback checked the'
        assert len(original) > 30000
        find.fill('Queue readback')
        assert dialog.locator('.evidence-original mark').inner_text() == 'Queue readback'
        assert 'Match 1 of 2' in dialog.locator('.evidence-find-status').inner_text()
        next_match = dialog.get_by_role('button', name='Next match')
        assert next_match.bounding_box()['height'] >= 44
        next_match.click()
        assert 'Match 2 of 2' in dialog.locator('.evidence-find-status').inner_text()
        assert dialog.locator('blockquote').inner_text() == original
        find.fill('not in this invented run')
        assert 'No match' in dialog.locator('.evidence-find-status').inner_text()
        assert not dialog.locator('.evidence-original mark').count()
        find.fill('.*')
        assert 'No match' in dialog.locator('.evidence-find-status').inner_text()
        find.fill('')
        assert dialog.locator('.evidence-find-status').inner_text() == ''
        assert dialog.locator('blockquote').inner_text() == original
        assert dialog.locator('.evidence-original mark.span').inner_text() == span
        assert find.is_visible()
        assert dialog.evaluate('e => e.scrollWidth <= e.clientWidth')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.evaluate('togglePrivate()', isolated_context=False)
        assert not find.is_visible()
        page.evaluate('togglePrivate()', isolated_context=False)
        assert find.is_visible()
        page.get_by_role('button', name='Close source context').click()
        assert cite.evaluate('e => e === document.activeElement')


def test_skill_opens_on_its_finding_and_keeps_usage_in_full_note(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
    page.evaluate("""() => {
      const r = byPath('skills/catalog/weekly-brief.md');
      const source = 'skill-record:' + 'a'.repeat(64);
      r.text = '# weekly-brief\\n\\n## Insight\\nA saved draft still needs a queue readback. [1]\\n\\nMore detail belongs in the note. [1]\\n\\n## When to use\\nUse for a weekly brief. [1]\\n\\n## Sources\\n- [1] ' + source;
      REM.source_context[source] = {source: 'skill-record', excerpt: 'Recorded queue readback.', truncated: false};
      KNOWN.delete(r.path);
      render();
    }""", isolated_context=False)
    assert page.locator('.focus-statement').inner_text() == 'A saved draft still needs a queue readback.'
    assert page.locator('.focus-head .focus-kicker').inner_text() == 'Useful finding'
    assert not page.locator('.focus-more').is_visible()
    finding_source = page.locator('.skill-finding-cites a.cite').first
    assert finding_source.get_attribute('href').endswith('h=src-1')
    assert finding_source.bounding_box()['width'] >= 44
    assert finding_source.bounding_box()['height'] >= 44
    finding_source.click()
    assert page.locator('#evidence-panel blockquote').inner_text() == 'Recorded queue readback.'
    page.get_by_role('button', name='Close source context').click()
    assert finding_source.evaluate('e => e === document.activeElement')
    page.get_by_role('link', name='View sources →').click()
    assert page.locator('.deep-note .block-sources').is_visible()
    assert 'Use for a weekly brief.' in page.locator('.deep-note').inner_text()
    page.locator('.deep-note a.cite').first.click()
    assert page.locator('#evidence-panel .evidence-claim').evaluate('e => e.scrollWidth <= e.clientWidth')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button', name='Close source context').click()
    page.evaluate("""() => {
      const r = byPath('skills/catalog/weekly-brief.md');
      r.text = r.text.replace('A saved draft still needs a queue readback. [1]',
        'A saved draft still needs a queue readback. [personal] [1]');
      KNOWN.delete(r.path);
      render();
    }""", isolated_context=False)
    private_source = page.locator('.skill-finding-cites a.cite').first
    assert private_source.is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not private_source.is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert private_source.is_visible()


def test_skill_activity_uses_invocation_dates_instead_of_investigation_dates(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=skills%2Fcatalog%2Ftalk-outline.md')
    assert 'Skill-name matches\n0' in page.locator('.focus-facts').inner_text()
    assert 'Last active' not in page.locator('.focus-facts').inner_text()
    assert 'Last name match' not in page.locator('.focus-facts').inner_text()
    assert 'last activity' not in page.locator('.eyebrow').inner_text()
    assert 'last name match' not in page.locator('.eyebrow').inner_text()
    assert 'file updated' in page.locator('.eyebrow').inner_text()
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
    assert 'Last name match' in page.locator('.focus-facts').inner_text()
    assert 'last name match' in page.locator('.eyebrow').inner_text()
    assert page.evaluate('known(byPath("skills/catalog/weekly-brief.md")).last === skillUsage(byPath("skills/catalog/weekly-brief.md")).last', isolated_context=False)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_skill_name_matches_are_not_presented_as_installed_version_runs(reader):
    page, uri = reader
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        page.goto(uri + '#r=skills%2Fcatalog%2Finvoice-check.md')
        page.evaluate("""() => {
          const r = byPath('skills/catalog/invoice-check.md');
          r.text = r.text.replace('## Source\\n',
            '## Run evidence\\n- Retained evaluation attempts: 0; installed version unverified.\\n\\n## Source\\n');
          KNOWN.delete(r.path);
          render();
        }""", isolated_context=False)
        assert 'Skill-name matches\n3' in page.locator('.focus-facts').inner_text()
        assert '3 skill-name matches' in page.locator('.lead-meta.usage').inner_text()
        assert 'retained eval attempts are counted separately' in page.locator('.usage-scope').inner_text()
        usage = page.locator('.panel').filter(has_text='Matched by skill name in coding sessions and co ai runs')
        assert usage.is_visible()
        assert 'Neither confirms this installed version or task outcome' in usage.inner_text()
        assert '3 matches in Claude Code' in usage.inner_text()
        assert 'Claude Code 3' not in page.locator('.leadrow').inner_text()
        assert 'Retained evaluation attempts: 0' in page.locator('.deep-note').inner_text()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')

    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=skills%2Fcatalog%2Finvoice-check.md')
    action = page.get_by_role('button', name='Copy investigation command')
    assert action.bounding_box()['y'] + action.bounding_box()['height'] <= 812
    assert page.locator('.missing.primary button').count() == 0


def test_skill_roster_links_are_touch_sized_on_phone(reader):
    page, uri = reader
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#c=skills')
    for link in page.locator('.hits.skills .t a').all():
        box = link.bounding_box()
        assert box['width'] >= 44 and box['height'] >= 44
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('.hits.skills .t a').first.click()
    assert page.locator('.record-focus.skills').is_visible()


def test_written_unknown_sections_are_distinct_from_uninvestigated_pages(reader):
    page, uri = reader
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
    page.evaluate("""() => {
      const r = byPath('skills/catalog/weekly-brief.md');
      r.written = true;
      r.text = '# weekly-brief\\n\\n## What it does\\nCheck the artifact.\\n\\n## Current status\\nUnknown — not verified\\n\\nInvestigation: investigated 2026-10-02';
      KNOWN.delete(r.path);
      render();
    }""", isolated_context=False)
    assert page.locator('.missing .names').inner_text() == 'Still unknown: Current status.'
    assert 'unresolved section' in page.locator('.missing .lead').inner_text().lower()
    page.goto(uri + '#r=people%2Fquinn-alder.md')
    assert page.locator('.missing .names').inner_text().startswith('Not investigated yet:')
    assert page.locator('.missing .lead').inner_text().lower() == 'only mapped so far'


def test_mapped_person_distinguishes_map_date_from_missing_note_fact(reader):
    page, uri = reader
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        page.reload()
        page.goto(uri + '#r=people%2Fquinn-alder.md')
        page.get_by_role('heading', name='Quinn Alder', exact=True).wait_for()
        assert 'Last contact in map' in page.locator('.leadrow').inner_text()
        assert page.locator('.focus-facts').count() == 0
        page.locator('details.deep-note > summary').click()
        assert '— map date shown above' in page.locator(
            '.factlist dt:text-is("Last contact") + dd').inner_text()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        if width == 375:
            page.locator('details.deep-note > summary').click()
            button = page.locator('.missing.primary .btn-primary').bounding_box()
            assert button['height'] >= 44
            assert button['y'] + button['height'] <= 812

        page.goto(uri + '#c=people')
        page.get_by_role('heading', name='People', exact=True).wait_for()
        quinn = page.locator('.sheet tbody tr').filter(has_text='Quinn Alder')
        assert 'map' in quinn.locator('.c-last').inner_text()

        page.goto(uri + '#r=people%2Fmara-ostrowski.md')
        page.get_by_role('heading', name='Mara Ostrowski', exact=True).wait_for()
        assert 'Last contact in map' not in page.locator('.leadrow').inner_text()

        page.goto(uri + '#r=people%2Fquinn-alder.md')
        page.get_by_role('heading', name='Quinn Alder', exact=True).wait_for()
        page.evaluate("""() => {
          const r = byPath('people/quinn-alder.md');
          r.last_activity = ''; r.mail.last = '';
          KNOWN.delete(r.path); FACTS.delete(r.path); render();
        }""", isolated_context=False)
        assert 'Last contact in map' not in page.locator('.leadrow').inner_text()
        page.locator('details.deep-note > summary').click()
        assert '— not found' in page.locator('.factlist dt:text-is("Last contact") + dd').inner_text()


def test_unknown_open_status_is_not_a_current_exchange(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.text = '# Harbour\\n\\n## Open threads\\nUnknown. Historical requests do not establish currently pending work. [1]\\n\\n## Sources\\n- [1] test:historical';
      KNOWN.delete(r.path);
      render();
    }""", isolated_context=False)
    assert page.evaluate("threads(byPath('projects/harbour.md')).items.length", isolated_context=False) == 0
    assert page.get_by_role('heading', name='Next exchanges').count() == 0
    page.locator('details.deep-note > summary').click()
    note = page.locator('.deep-note')
    assert 'Historical requests do not establish currently pending work.' in note.inner_text()
    assert note.locator('a.cite[href$="h=src-1"]').first.is_visible()


def test_project_map_date_is_labelled_as_a_session_not_verified_activity(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate("""() => {
      const r = byPath('projects/harbour.md');
      r.last_activity = '2026-09-16';
      KNOWN.delete(r.path); render();
    }""", isolated_context=False)
    assert 'Last mapped session' not in page.locator('.leadrow').inner_text()
    assert 'Last mapped session' in page.locator('.focus-facts').inner_text()
    assert 'last mapped session' in page.locator('.eyebrow').inner_text()
    assert 'Last active' not in page.locator('.leadrow').inner_text()
    page.goto(uri + '#c=projects')
    assert 'Last mapped session' in page.locator('.sheet thead').inner_text()


def test_completed_delivery_is_conversation_instead_of_a_commitment(reader):
    page, url = reader
    page.evaluate(r"""() => {
      const r = byPath('people/mara-ostrowski.md');
      const start = r.text.indexOf('## History');
      const end = r.text.indexOf('\n## ', start + 1);
      r.text = r.text.slice(0, start) + '## History\n- 2026-09-25: You sent company introductions [1].\n- 2026-09-26: You promised to send the revised overview [1].\n' + r.text.slice(end);
      KNOWN.clear(); FACTS.clear();
    }""", isolated_context=False)
    page.goto(url + '#r=people%2Fmara-ostrowski.md')
    rows = page.locator('.activity-list li')
    delivered = rows.filter(has_text='You sent company introductions')
    promised = rows.filter(has_text='You promised to send')
    assert delivered.get_attribute('data-type') == 'Conversation'
    assert promised.get_attribute('data-type') == 'Commitment'
    assert delivered.is_visible() and promised.is_visible()
    assert page.locator('.recent-activity .activity-filters').count() == 0


def test_marked_sentence_with_a_markdown_link_and_code_respects_private_mode(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r"""() => {
      const r = byPath('people/mara-ostrowski.md');
      r.text += '\n\n## Private context\nPublic setup. [Quinn](quinn-alder.md) shared confidential details in `case.txt` [sensitive] [1]. Public follow-up.\n';
      KNOWN.delete(r.path); render();
    }""", isolated_context=False)
    page.locator('details.deep-note > summary').click()
    sentence = page.locator('.deep-note .private').filter(has_text='confidential details')
    assert sentence.locator('.privacy-tag.sensitive').is_visible()
    assert sentence.locator('a:not(.cite)').inner_text() == 'Quinn'
    assert sentence.locator('code').inner_text() == 'case.txt'
    assert sentence.locator('a.cite').count() == 1
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not sentence.is_visible()
    assert not page.locator('.deep-note a').filter(has_text='Quinn').is_visible()
    assert not page.locator('.deep-note code').filter(has_text='case.txt').is_visible()
    assert page.get_by_text('Public setup.', exact=False).is_visible()
    assert 'Public follow-up.' in page.locator('.deep-note').inner_text()
    visible = page.locator('.deep-note p').filter(has_text='Public setup.').inner_text()
    assert ' '.join(visible.split()) == 'Public setup. Public follow-up.'
    page.evaluate('togglePrivate()', isolated_context=False)
    assert sentence.is_visible()


def test_consecutive_marked_sentences_hide_in_the_lead_and_full_note(reader):
    page, uri = reader
    page.goto(uri + '#r=orgs%2Ffernhill-labs.md')
    page.evaluate(r"""() => {
      const r = byPath('orgs/fernhill-labs.md');
      const paragraph = '## Our relationship\n' +
        'First confidential finding. [sensitive] [1][2][3] ' +
        'Second confidential finding. [sensitive] [1][2][3] ' +
        'Public result. [1] ' +
        '[Quinn](../people/quinn-alder.md) sent `secret-value`. [personal] [1]\n\n';
      r.text = r.text.replace('## Who they are', paragraph + '## Who they are');
      KNOWN.delete(r.path); render();
    }""", isolated_context=False)
    for selector in ('.focus-statement', '.deep-note'):
        area = page.locator(selector)
        assert area.locator('.private').count() == 3
        assert area.locator('.private').filter(has_text='Second confidential finding').count() == 1
    assert page.locator('.deep-note .private a.cite').count() == 3
    page.evaluate('togglePrivate()', isolated_context=False)
    for selector in ('.focus-statement', '.deep-note'):
        text = page.locator(selector).inner_text()
        assert 'confidential finding' not in text
        assert 'secret-value' not in text
        assert 'Public result.' in text
    page.evaluate('togglePrivate()', isolated_context=False)
    assert 'Second confidential finding' in page.locator('.focus-statement').inner_text()
    assert page.locator('.deep-note .private code').is_visible()


def test_connected_context_hides_private_bases_including_expanded_connections(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r"""() => {
      const r = byPath('people/mara-ostrowski.md');
      r.relations = Array.from({length: 7}, (_, n) => ({path: 'projects/harbour.md',
        kind: n === 6 ? 'mentioned by' : 'linked', private: n === 0 || n === 6,
        basis: n === 0 || n === 6 ? 'Confidential background' : 'Public pilot context'}));
      render();
    }""", isolated_context=False)
    assert page.locator('details.deep-note').get_attribute('open') is None
    page.locator('details.deep-note > summary').click()
    page.locator('.more-relations > summary').first.click()
    bases = page.locator('.relation-basis').filter(has_text='Confidential background')
    assert bases.count() == 2
    assert all(bases.nth(n).is_visible() for n in range(2))
    page.evaluate('togglePrivate()', isolated_context=False)
    assert all(not bases.nth(n).is_visible() for n in range(2))
    assert page.locator('.relation-basis').filter(has_text='Public pilot context').first.is_visible()
    assert page.locator('.relation-card strong').first.is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert all(bases.nth(n).is_visible() for n in range(2))


@pytest.mark.parametrize('width', [390, 1440])
def test_failed_init_is_visible_and_keyboard_reachable(reader, tmp_path, monkeypatch, width):
    from connectonion.rem import reader as rem_reader

    page, _ = reader
    data = rem_reader.snapshot(tmp_path / 'rem')
    data['as_of'] = '2026-10-07T12:00:00+00:00'
    data['logs'] = [
        {'started_at': '2026-10-07T11:00:00+00:00', 'outcome': 'failed',
         'error': 'Failed to authenticate. API Error: 403 Request not allowed', 'changed': []},
        {'started_at': '2026-10-07T11:01:00+00:00', 'outcome': 'failed',
         'error': 'TimeoutError: private payload must not appear here', 'changed': []},
    ]
    monkeypatch.setattr(rem_reader, 'snapshot', lambda _, local=False: data)
    path = tmp_path / 'blocked.html'
    path.write_text(rem_reader.render(tmp_path / 'rem'))
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(path.as_uri())
    brief = page.locator('.overnight')
    assert '2 investigations failed' in brief.inner_text()
    assert 'Model access was refused' in brief.inner_text()
    assert 'A request timed out' in brief.inner_text()
    assert 'private payload' not in brief.inner_text()
    assert 'No memory pages were written' in brief.inner_text()
    assert page.locator('.night-details .hypno .dot.woke').count() == 2
    link = brief.get_by_role('link', name='Review failed runs →')
    assert link.bounding_box()['height'] >= 44
    link.focus()
    link.press('Enter')
    page.get_by_role('heading', name='Activity', exact=True).wait_for()
    assert page.locator('.activity-runs li.failed-run').count() == 2
    assert 'private payload' not in page.locator('.activity-runs').inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_partial_pass_keeps_written_memory_beside_failure(reader, tmp_path, monkeypatch):
    from connectonion.rem import reader as rem_reader

    page, _ = reader
    data = rem_reader.snapshot(tmp_path / 'rem')
    data['logs'] = [
        {'started_at': data['as_of'], 'outcome': 'completed',
         'changed': ['people/mara-ostrowski.md']},
        {'started_at': data['as_of'], 'outcome': 'failed', 'error': 'TimeoutError', 'changed': []},
    ]
    monkeypatch.setattr(rem_reader, 'snapshot', lambda _, local=False: data)
    path = tmp_path / 'partial.html'
    path.write_text(rem_reader.render(tmp_path / 'rem'))
    page.goto(path.as_uri())
    brief = page.locator('.overnight')
    assert '1 investigation failed' in brief.inner_text()
    assert 'reworded; nothing new.' in brief.inner_text()
    assert page.locator('.week').get_by_role('link', name='Mara Ostrowski', exact=True).is_visible()
    assert page.locator('.waiting-ledger > li').count() > 0
    assert 'No memory pages were written' not in brief.inner_text()


WHOLE_WORDS = """([selector, words]) => words.every(word => [...document.querySelectorAll(selector)].every(node => {
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const text = walker.currentNode, at = text.data.indexOf(word);
    if (at < 0) continue;
    const range = document.createRange();
    range.setStart(text, at); range.setEnd(text, at + word.length);
    if (new Set([...range.getClientRects()].map(r => Math.round(r.top))).size > 1) return false;
  }
  return true;
}))"""


@pytest.mark.parametrize('width', [390, 1440])
def test_fact_labels_and_addresses_never_break_mid_word(reader, width):
    page, uri = reader
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.locator('details.deep-note > summary').click()
    page.locator('.factlist dt').first.wait_for()
    assert page.evaluate(WHOLE_WORDS, ['.factlist dt', ['REPOSITORY', 'ORGANISATION', 'Repository', 'Organisation']])
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace(/- Email: [^\\n]+/, '- Email: 0x3c3ae74550@mail.openonion.ai [1]')
        .replace(/## Facts\\n/, '## Facts\\n- Handles: 0x3c3ae74550@mail.openonion.ai [1]\\n');
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    page.locator('details.deep-note > summary').click()
    page.locator('.factlist dd').first.wait_for()
    assert page.evaluate(WHOLE_WORDS, ['.factlist dd, .contact-strip dd', ['0x3c3ae74550', 'openonion', 'mail']])
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_long_hash_ids_are_shortened_with_the_full_id_on_hover(reader):
    page, uri = reader
    digest = '1831aa83d8a03a4013b38bf560ea93cc1279c281cee147ce426980c4028e4080'
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
    page.evaluate("""(digest) => {
      const r = byPath('skills/catalog/weekly-brief.md');
      r.text = '# weekly-brief\\n\\n## Insight\\nA saved draft needs a queue readback. [1]\\n'
        + '\\n## Usage history\\n- 2026-10-09 · Run record `skill-record:' + digest + '`; output unavailable. [1]\\n'
        + '\\n## Sources\\n- [1] skill-record:' + digest + ' — 2026-10-09';
      KNOWN.delete(r.path); render();
    }""", digest, isolated_context=False)
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md&h=sources')
    page.locator('.deep-note .block-sources').wait_for(state='visible')
    note = page.locator('.deep-note').inner_text()
    assert digest not in note
    assert 'skill-record:1831aa83d8a0…' in note
    assert page.locator('.block-sources .id').first.get_attribute('title') == 'skill-record:' + digest
    assert page.locator('.deep-note code[title="skill-record:' + digest + '"]').count() == 1


def test_the_sidebar_has_one_activity_entry_after_the_memory_categories(reader, tmp_path, monkeypatch):
    """Owner, 2026-10-15: "Run logs" and "AI notes" read as the same thing twice."""
    from connectonion.rem import reader as rem_reader
    from connectonion.rem.files import Notebook

    page, _ = reader
    notebook = Notebook(tmp_path / 'rem')
    notebook.write('notes/reflection.md', '# A reflection\n\nWhat the last pass taught.\n')
    notebook.write('logs/people-map.md', '# People map\n\nWho writes to whom.\n')
    notebook.write('logs/skill-runs-0123456789ab.md', '# weekly-brief runs\n\nRun coverage.\n')
    path = tmp_path / 'activity.html'
    path.write_text(rem_reader.render(tmp_path / 'rem'))
    page.goto(path.as_uri())
    nav = page.locator('#nav a').all_inner_texts()
    assert not any('Run logs' in item or 'AI notes' in item for item in nav)
    labels = [item.split('\n')[0] for item in nav]
    assert labels[-1] == 'Activity' and labels.index('All records') < labels.index('Activity')
    listed = page.evaluate('listedRecords().map(r => r.path)', isolated_context=False)
    assert not [path for path in listed if path.startswith(('logs/', 'notes/'))]
    assert page.locator('#nav a[href="#c=all"] .n').inner_text() == str(len(listed))
    assert 'Maps' not in page.locator('.category-cards').inner_text()
    page.goto(path.as_uri() + '#q=coverage')
    assert 'weekly-brief runs' not in page.locator('#main').inner_text()
    page.goto(path.as_uri() + '#r=logs%2Fskill-runs-0123456789ab.md')
    assert page.get_by_role('heading', name='weekly-brief runs').is_visible()


@pytest.mark.parametrize('width', [375, 1440])
def test_activity_lists_each_run_with_pages_changed_and_refused(reader, tmp_path, monkeypatch, width):
    from connectonion.rem import reader as rem_reader
    from connectonion.rem.files import Notebook

    page, _ = reader
    Notebook(tmp_path / 'rem').write('logs/people-map.md', '# People map\n\nWho writes to whom.\n')
    data = rem_reader.snapshot(tmp_path / 'rem')
    data['logs'] = [{'started_at': data['as_of'], 'outcome': 'completed', 'phase': 'daily-update', 'items': 40,
                     'usage': {'input_tokens': 1200, 'output_tokens': 300}, 'changed': ['people/mara-ostrowski.md'],
                     'refusals': [{'record': 'projects/harbour.md',
                                   'errors': ['Candidate rejected, kept at /private/c.md: Changed page has no numbered evidence references']}]}]
    monkeypatch.setattr(rem_reader, 'snapshot', lambda _, local=False: data)
    path = tmp_path / 'runs.html'
    path.write_text(rem_reader.render(tmp_path / 'rem'))
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(path.as_uri() + '#view=activity')
    run = page.locator('.activity-runs > li')
    assert run.count() == 1
    text = run.inner_text()
    assert 'daily-update' in text and '40 read' in text and '1,200 in / 300 out tokens' in text
    assert run.get_by_role('link', name='Mara Ostrowski').is_visible()
    assert run.get_by_role('link', name='Harbour').is_visible()
    assert 'Changed page has no numbered evidence references' in text and '/private/c.md' not in text
    maps = page.locator('details.activity-shelf')
    assert maps.inner_text().startswith('Maps · 1') and not maps.evaluate('(node) => node.open')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.goto(path.as_uri())
    assert page.locator('details.maint a[href="#view=activity"]').count() == 1


def test_citations_name_the_source_and_open_marked_margin_or_sheet(reader):
    page, uri = reader
    for width in (1400, 390, 375):
        page.set_viewport_size({'width': width, 'height': 844})
        page.goto(uri + '#r=people%2Fmara-ostrowski.md')
        page.evaluate("""() => {
          const r = byPath('people/mara-ostrowski.md');
          r.text = r.text.replace("the pilot's renewal depends on two things you each owe the other [4][5].",
            'Mara promised “I will send the usage export” by Friday. [5]');
          Object.assign(REM.source_context['outlook:77c09ad1e3f0'], {
            sender: 'Mara Ostrowski <mara@fernhill.example>', time: '2026-10-14T10:33:00Z',
            participants: {from: 'Mara Ostrowski <mara@fernhill.example>', to: ['Avery <avery@example.test>']},
            excerpt: 'Hello Avery,\\nI will   send the usage export by Friday. Thanks, Mara.'
          });
          KNOWN.clear(); FACTS.clear(); render();
        }""", isolated_context=False)
        chip = page.locator('.person-insight a.cite[href$="src-5"]').first
        assert chip.inner_text() == 'Mara, Outlook, 14 Oct'
        assert 'subject “Harbour renewal”' in chip.get_attribute('aria-label')
        assert 'data-tip' not in chip.evaluate('e => e.outerHTML')
        box = chip.bounding_box()
        assert box['height'] >= 24 and box['width'] >= 24
        chip.click()
        panel = page.locator('#evidence-panel')
        assert panel.is_visible()
        assert 'Source 1 of 1 for this line' in panel.locator('.evidence-top').inner_text()
        assert panel.locator('.evidence-claim mark.span').inner_text() == 'I will send the usage export'
        assert panel.locator('.msg-body mark.span').inner_text() == 'I will   send the usage export'
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        bounds = panel.bounding_box()
        assert panel.evaluate('e => e.scrollWidth <= e.clientWidth')
        if width >= 1100:
            assert bounds['width'] == 380 and bounds['y'] == 16
            assert panel.get_attribute('aria-modal') == 'false'
            assert chip.bounding_box()['x'] + chip.bounding_box()['width'] < bounds['x']
            assert not page.locator('.evidence-backdrop').is_visible()
        else:
            assert bounds['y'] > 0 and bounds['height'] <= 844 * .75 + 1
            assert abs(bounds['y'] + bounds['height'] - 844) <= 1
            assert panel.get_attribute('aria-modal') == 'true'
            assert page.locator('.evidence-handle').is_visible()
            page.keyboard.press('/')
            assert panel.evaluate('e => e.contains(document.activeElement)')
            page.keyboard.press('Shift+Tab')
            assert panel.evaluate('e => e.contains(document.activeElement)')
            page.keyboard.press('Tab')
            assert panel.evaluate('e => e.contains(document.activeElement)')
            page.locator('.evidence-backdrop').click(position={'x': 5, 'y': 5})
            assert not panel.is_visible()
            assert chip.evaluate('e => e === document.activeElement')
            chip.click()
        page.keyboard.press('Escape')
        assert not panel.is_visible()
        assert chip.evaluate('e => e === document.activeElement')
        assert page.locator('#evidence-panel').count() == 1


def test_citation_labels_fallback_and_grouped_sources_stay_honest(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    values = page.evaluate("""() => {
      const r = byPath('people/mara-ostrowski.md');
      const context = REM.source_context['outlook:77c09ad1e3f0'];
      const owner = byPath(REM.owner);
      owner.index = {...owner.index, emails: ['owner@example.test']};
      context.sender = 'Owner <owner@example.test>';
      context.participants = {};
      context.time = '2026-10-14T10:33:00Z';
      return [chipLabel(r, '5'), chipLabel(r, '1'), chipLabel(r, '99'),
        sourceChannel('claude-session'), sourceChannel('project-source'), sourceChannel('whatsapp')];
    }""", isolated_context=False)
    assert values == ['you, Outlook, 14 Oct', 'Outlook, 22 Aug', 'source 99', 'Session', 'Repo', 'WhatsApp']
    page.locator('details.deep-note > summary').click()
    missing = page.locator('.factlist a.cite[href$="src-1"]').first
    assert 'missing' in missing.get_attribute('class')
    assert 'original not in this snapshot' in missing.get_attribute('aria-label')
    missing.click()
    panel = page.locator('#evidence-panel')
    assert panel.locator('.evidence-unavailable').inner_text() == "The original isn't in this snapshot."
    page.get_by_role('button', name='Close source context').click()
    grouped = page.locator('.person-insight .cite.run')
    assert grouped.inner_text().endswith(' +2')
    grouped.click()
    assert 'Source 1 of 3 for this line' in panel.locator('.evidence-top').inner_text()
    panel.get_by_role('combobox', name='Source for this line').select_option('5')
    assert 'Source 2 of 3 for this line' in panel.locator('.evidence-top').inner_text()
    assert 'I will send the usage export' in panel.locator('.msg-body').inner_text()
    page.get_by_role('button', name='Close source context').click()
    assert grouped.evaluate('e => e === document.activeElement')
    page.evaluate("""() => {
      const r = byPath('people/mara-ostrowski.md');
      document.getElementById('main').appendChild(el('p', {id: 'missing-citation', html: inline('No original [99].', r.path)}));
    }""", isolated_context=False)
    absent = page.locator('#missing-citation a.cite')
    assert absent.inner_text() == 'source 99'
    absent.click()
    assert panel.locator('.evidence-unavailable').inner_text() == "The original isn't in this snapshot."
    page.get_by_role('button', name='Close source context').click()
    assert absent.evaluate('e => e === document.activeElement')


def test_supporting_span_preserves_words_and_never_invents_a_match(reader):
    page, _ = reader
    result = page.evaluate("""() => [
      supportingSpan('She said “send the signed form”.', 'Please SEND  the signed form today.'),
      supportingSpan('Please send the signed form today.', 'Hello, send the signed form tomorrow.'),
      supportingSpan('She said "a missing quotation".', 'She said a different thing.'),
      supportingSpan('Send the form.', 'Send the form.'),
      markedSpan('<script>alert(1)</script>', [0, 8])
    ]""", isolated_context=False)
    assert result[0] == {'claim': [10, 30], 'source': [7, 28]}
    assert result[1] == {'claim': [7, 27], 'source': [7, 27]}
    assert result[2] is None and result[3] is None
    assert '<script>' not in result[4] and '&lt;script&gt;' in result[4]


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [375, 390, 1400])
def test_person_ledger_discloses_extra_rows_and_deep_hash_targets(reader, theme, width):
    page, uri = reader
    page.emulate_media(color_scheme=theme)
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r"""() => {
      REM.as_of = '2026-10-15T12:00:00Z'; REM.status.timezone = 'UTC';
      const r = byPath('people/mara-ostrowski.md');
      const rows = [
        '- The user owes Mara: a signed draft; since 2026-10-08 [4].',
        '- The user owes Mara a scope decision; due: 2026-10-22 [5].',
        '- The user owes Mara: an old receipt; since 2026-07-22 [6].',
        '- The user owes Mara: a fourth answer [1].',
        '- Mara owes the user: the usage export [5].',
        '- Yu owes Ody: a reimbursement [1].'
      ];
      r.text = r.text.replace(/## Open threads[\s\S]*?(?=\n## )/, '## Open threads\n' + rows.join('\n') + '\n');
      r.text = r.text.replace(/- Now:/, '- **Now**:').replace(/- At stake:/, '- **At stake**:');
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    mine = page.locator('.ledger-column.mine')
    assert mine.locator('.ledger-count').inner_text() == '4'
    assert mine.locator('.ledger-rows').first.locator(':scope > li').count() == 3
    assert mine.locator('.ledger-row').filter(has_text='fourth answer').is_visible() is False
    assert 'You owe' not in mine.locator('.ledger-row p').first.inner_text()
    assert 'A scope decision; due:' in mine.inner_text()
    assert '7 days' in mine.inner_text() and '85 days, gone quiet' in mine.inner_text()
    assert page.locator('.ledger-column.theirs .ledger-count').inner_text() == '1'
    assert 'Yu owes Ody' not in page.locator('.between-you').inner_text()
    mine.locator('.ledger-more > summary').click()
    assert mine.locator('.ledger-row').filter(has_text='fourth answer').is_visible()
    assert page.locator('.person-insight dt.at-stake').inner_text() == 'At stake'
    assert page.locator('.person-insight dt').count() <= 4
    assert page.locator('.recent-activity .activity-list > li').count() <= 5
    assert page.locator('.deep-note .block-threads, .deep-note .block-insight').count() == 0
    assert page.locator('details.deep-note').get_attribute('open') is None
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('.recent-activity .activity-head a').click()
    assert page.locator('details.deep-note').get_attribute('open') is not None
    assert page.locator('#history').is_visible()
    page.goto(uri + '#r=people%2Fmara-ostrowski.md&h=src-6')
    assert page.locator('details.deep-note').get_attribute('open') is not None
    assert page.locator('#src-6').is_visible()


def test_morning_rows_quote_only_original_words_and_format_overdue_dates(reader):
    page, _ = reader
    values = page.evaluate(r"""() => {
      REM.as_of = '2026-10-15T12:00:00Z'; REM.status.timezone = 'UTC';
      const r = {title: 'Weiwei Lei'};
      return [morningWords('The user owes Weiwei Lei a draft; send questions afterward [5].', r),
        morningWords('You owe Weiwei Lei a draft; due: 2026-10-22 [5].', r),
        morningWords('Weiwei asked “Send the draft and questions.” [5].', r),
        morningWords('You owe Weiwei Lei "ok" and a draft [5].', r),
        dueLabel({due: '2026-09-10'}), direction('You said you would send what Weiwei owes the bank')];
    }""", isolated_context=False)
    assert values[0] == {'words': 'A draft', 'context': 'send questions afterward. [5]'}
    assert values[1]['words'] == 'A draft' and 'due: 2026-10-22' in values[1]['context']
    assert values[2]['words'] == '“Send the draft and questions.”' and '[5]' in values[2]['context']
    assert not values[3]['words'].startswith('“')
    assert values[4] == 'overdue · 10 Sep'
    assert values[5] != 'third'


def test_morning_selection_keeps_distinct_pages_and_named_obligations(reader):
    page, _ = reader
    got = page.evaluate(r"""() => {
      const mara = byPath('people/mara-ostrowski.md'), tomas = byPath('people/tomas-reyes.md');
      const ines = byPath('people/ines-halvorsen.md'), project = byPath('projects/harbour.md');
      const item = (r, text) => ({r, t: {text, dir: 'mine', quiet: false}});
      return morningEntries([
        item(mara, 'You owe Tomás a talk abstract [1].'),
        item(mara, 'You owe Mara the signed draft [4].'),
        item(mara, 'You owe Mara a second answer [5].'),
        item(tomas, 'You owe Tomás the signed draft [1].'),
        item(project, 'You owe Tomás Reyes the signed draft [1].'),
        item(ines, 'You owe Inès the Q3 receipts [1].'),
        item(project, 'You owe Harbour a deployment [1].')
      ]).map(({r, t}) => [r.path, t.text]);
    }""", isolated_context=False)
    assert [row[0] for row in got] == ['people/mara-ostrowski.md', 'people/tomas-reyes.md', 'people/ines-halvorsen.md']
    assert 'signed draft' in got[1][1]


def test_project_focus_and_deep_note_do_not_repeat_purpose_or_threads(reader):
    page, uri = reader
    page.goto(uri + '#r=projects%2Fharbour.md')
    page.evaluate(r"""() => {
      const r = byPath('projects/harbour.md');
      r.text += '\n## Insight\n- Now: The pilot needs a release decision [1].\n';
      r.text = r.text.replace(/## Open threads[\s\S]*?(?=\n## )/,
        '## Open threads\n' + [1,2,3,4,5].map(n => '- You owe Mara obligation ' + n + ' [1].').join('\n') + '\n');
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    assert page.locator('.lead-open').count() == 0
    assert page.locator('.next-exchanges .thread').count() == 3
    assert page.locator('#what-it-is').count() == 1
    assert page.locator('.project-workspace h2').filter(has_text='What this is').count() == 0
    page.locator('details.deep-note > summary').click()
    assert page.locator('.deep-note .block-threads .thread').count() == 2
    assert 'obligation 1' not in page.locator('.deep-note .block-threads').inner_text()
    assert page.locator('.deep-note #what-it-is').count() == 0
    page.goto(uri + '#r=projects%2Fharbour.md&h=what-it-is')
    assert page.locator('#what-it-is').is_visible()


def test_morning_keeps_separate_people_with_the_same_kind_of_request(reader):
    page, _ = reader
    assert page.evaluate(r"""() => {
      const people = ['people/mara-ostrowski.md', 'people/tomas-reyes.md', 'people/ines-halvorsen.md'].map(byPath);
      return morningEntries(people.map(r => ({r, t: {text: 'You owe ' + r.title + ' a reply [1].', dir: 'mine', quiet: false}}))).length;
    }""", isolated_context=False) == 3
