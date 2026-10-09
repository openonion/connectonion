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
            assert "NEEDS YOUR EXPLICIT REQUEST" in page.locator(".focus-kicker").inner_text()
            assert "Automatic investigation skips this private project." in page.locator(".missing").inner_text()
            assert "investigate 'projects/journal.md'" in page.locator(".missing .cmd").inner_text()
            assert page.get_by_role("button", name="Copy the command").is_visible()
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
        page.get_by_role("heading", name="What co rem carried forward").wait_for()
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
    monkeypatch.setattr(rem_reader, "snapshot", lambda _: data)
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
    monkeypatch.setattr(rem_reader, "snapshot", lambda _: data)
    path = tmp_path / "first-map.html"
    path.write_text(rem_reader.render(tmp_path / "rem"), encoding="utf-8")

    page, _ = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(path.as_uri())
    assert page.get_by_role("heading", name="Your source map").is_visible()
    assert page.locator(".first-map h2").inner_text().endswith(" records mapped")
    assert page.locator(".first-map .morning-time").inner_text() == "0 memories written"
    assert page.locator(".first-map-actions a").inner_text() == f"Browse {visible_people} people →"
    assert page.locator(".first-map-actions a").is_visible()
    assert page.locator(".first-map-actions button").evaluate("e => e.getBoundingClientRect().bottom <= innerHeight")
    assert "Background updates off" in page.locator("#mobile-status").inner_text()
    page.locator(".first-map-actions a").click()
    assert "1 possible contact" in page.locator(".held-note").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_a_person_opens_on_a_fact_card_with_cited_values(reader):
    page, _ = reader
    page.goto(page.url.split("#")[0] + "#r=people%2Fmara-ostrowski.md")
    # Under the title: what you owe and for how long.
    lead = page.locator(".leadrow .lead-open")
    assert lead.locator(".dir").inner_text().upper() == "YOU OWE" and lead.locator(".age").inner_text() == "open for 9 days"
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


def test_grouped_citation_sources_are_each_openable_on_phone(reader):
    page, uri = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    assert page.locator(".insight .cite.run").count() == 1
    page.locator("#src-6 .source-open").click()
    assert "source 6" in page.locator("#evidence-dialog .evidence-top").inner_text().lower()
    assert page.locator("#evidence-dialog .evidence-original").is_visible()
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
    # A thread addressed to the owner by name ("Avery: collect …") is the owner's to do.
    assert page.evaluate("direction('Avery: collect the swipe card from Security')", isolated_context=False) == "mine"
    home_threads = page.locator("ul.threads").first.inner_text()
    assert "you have owed them" in home_threads and "the user" not in home_threads.lower()
    page.goto(page.url.split("#")[0] + "#r=people%2Fmara-ostrowski.md")
    main = page.locator("#main").inner_text()
    assert "the user" not in main.lower() and "you have not signed it" in main
    assert page.get_by_role("heading", name="How you write to them").count() == 1
    assert page.evaluate("REM.records.find(r => r.path === 'people/mara-ostrowski.md').text.includes('the user has not signed it')", isolated_context=False)


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
    page.locator(".conversation-open").first.click()
    dialog = page.locator("#conversation-dialog")
    assert dialog.is_visible() and "usage export" in dialog.inner_text()
    dialog.get_by_role("button", name="Close conversation").click()
    assert page.locator(".conversation-open").first.evaluate("e => document.activeElement === e")
    page.locator("a.cite[href*='src-5']").first.click()
    evidence = page.locator("#evidence-dialog")
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
    assert 'I will send the usage export' in page.locator('#evidence-dialog').inner_text()


def test_short_focus_text_clipped_on_phone_can_expand_and_collapse(reader):
    page, uri = reader
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    statement = "Mara needs the revised pilot agreement before deciding whether her team can renew, including the usage export, the pricing proposal, and a signed data-sharing addendum by Friday."
    assert len(statement) < 180
    page.evaluate("text => { const r = byPath('people/mara-ostrowski.md'); r.text = '# Mara Ostrowski\\n\\n' + text; KNOWN.clear(); FACTS.clear(); render(); }", statement, isolated_context=False)
    lead = page.locator('.focus-statement')
    assert lead.evaluate('e => e.scrollHeight > e.clientHeight')
    more = page.locator('.focus-more')
    assert more.is_visible()
    more.click()
    assert more.get_attribute('aria-expanded') == 'true'
    assert lead.evaluate('e => e.scrollHeight <= e.clientHeight + 1')
    page.get_by_role('button', name='Show less', exact=True).click()
    assert more.get_attribute('aria-expanded') == 'false'
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.wait_for_function("document.querySelector('.focus-more').hidden")


def test_record_dates_do_not_disagree_when_the_index_is_stale(reader):
    page, uri = reader
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    expected = page.evaluate("known(byPath('people/mara-ostrowski.md')).last", isolated_context=False)
    page.evaluate("() => { byPath('people/mara-ostrowski.md').index = {last_contact: '2001-01-01'}; FACTS.clear(); render(); }", isolated_context=False)
    formatted = page.evaluate('date => fmtDate(date)', expected, isolated_context=False)
    # The contact strip leaves dates to the headline's last-contact line (#2104).
    assert formatted in page.locator('.lead-meta').inner_text()
    assert '2001' not in page.locator('.lead-meta').inner_text()
    assert formatted in page.locator('.factlist dt:text-is("Last contact") + dd').inner_text()


def test_empty_mail_keeps_private_header_evidence_without_inventing_a_body_excerpt(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("""() => {
      Object.assign(REM.source_context['outlook:77c09ad1e3f0'], {
        source: 'outlook', excerpt: '', body_empty: true, truncated: false, subject: 'Accepted: Workshop',
        participants: {from: 'mara@example.org', to: ['owner@example.org'], cc: []}
      });
    }""", isolated_context=False)
    for width in (1440, 375):
        page.set_viewport_size({'width': width, 'height': 812})
        trigger = page.locator('.deep-note a.cite[href$="h=src-5"]').first
        trigger.click()
        dialog = page.locator('#evidence-dialog')
        assert 'MAIL HEADERS' in dialog.inner_text()
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
    page.locator('.conversation-open').first.click()
    messages = page.locator('#conversation-dialog .conversation-message')
    assert messages.first.is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not messages.first.is_visible()
    assert page.locator('#conversation-dialog .private-hidden-notice').is_visible()
    page.get_by_role('button', name='Close conversation').click()
    page.locator("a.cite[href*='src-5']").first.click()
    original = page.locator('#evidence-dialog .evidence-original')
    assert original.count() == 1 and not original.is_visible()
    assert page.locator('#evidence-dialog .private-hidden-notice').is_visible()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert original.is_visible() and 'I will send the usage export' in original.inner_text()


def test_private_project_summary_and_partial_scope_are_clear_on_desktop_and_phone(reader):
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
        assert '3 session inputs were supplied' in page.locator('.scope-note').inner_text()
        assert '5 inputs are archived' in page.locator('.scope-note').inner_text()
        assert 'clamped' not in page.locator('.focus-statement').get_attribute('class')
        page.evaluate('togglePrivate()', isolated_context=False)
        assert page.locator('.focus-statement').inner_text() == 'Hidden labelled passage'
        assert page.locator('.project-purpose-preview').inner_text() == 'Hidden labelled passage'
        assert page.locator('.project-workspace').get_by_text('Hidden labelled passage').count() == 2
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


def test_project_without_a_current_insight_leads_with_purpose_and_scope(reader):
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
        assert page.locator('.focus-kicker').first.inner_text() == 'WHAT THIS PROJECT DOES'
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
        assert '5 inputs are archived for this workspace' in page.locator('.scope-note').inner_text()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_written_project_purpose_precedes_partial_scope_on_phone(reader):
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
    scope = page.locator('.scope-note')
    assert 'property lead workflow' in purpose.inner_text()
    assert purpose.bounding_box()['y'] < 812
    assert purpose.bounding_box()['y'] < scope.bounding_box()['y']
    assert '114 session inputs' in scope.inner_text()
    purpose_source = page.locator('.project-purpose-cites a.cite').first
    assert purpose_source.get_attribute('aria-label') == 'Source 1'
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
    assert 'weekly brief before a renewal call' in page.locator('.deep-note').inner_text()
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
    others = page.locator('.band', has=page.locator('h3 span:text-is("Waiting on others")'))
    plain = page.locator('.band', has=page.locator('h3 span:text-is("Other open context")'))
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
        assert (background == "rgb(13, 16, 26)") == (theme == "dark"), (view, background)


def test_source_and_conversation_show_input_limits_and_hide_them_with_private_content(reader):
    page, uri = reader
    scope = 'Codex Desktop voice transcription; only explicit input, transcript delta omitted; recognition errors possible'
    page.set_viewport_size({'width': 375, 'height': 812})
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate("scope => { const c = REM.source_context['outlook:77c09ad1e3f0']; c.input_scope = scope; REM.conversations[c.thread].messages[0].input_scope = scope; }", scope, isolated_context=False)
    page.locator("a.cite[href*='src-5']").first.click()
    note = page.locator('#evidence-dialog .evidence-input-scope')
    assert note.is_visible() and 'Transcription may contain errors.' in note.inner_text() and 'transcript delta' not in note.inner_text()
    page.evaluate('togglePrivate()', isolated_context=False)
    assert not note.is_visible()
    page.get_by_role('button', name='Close source context').click()
    page.evaluate('togglePrivate()', isolated_context=False)
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
    dialog = page.locator('#evidence-dialog')
    participants = dialog.locator('.evidence-participants')
    assert participants.is_visible()
    head = dialog.locator('.msg-head').inner_text()
    assert 'Mentor' in head and 'mentor@example.org' in head
    assert 'Cc' in participants.inner_text() and 'Guest' in participants.inner_text()
    assert participants.locator('[title="guest@example.org"]').count() == 1
    assert 'Sent ' in dialog.inner_text() and 'Archived ' in dialog.inner_text()
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
    row = page.locator('.next-exchanges .thread').first
    assert row.locator('.when').inner_text() == 'due today'
    title = row.locator('.when').get_attribute('title')
    assert 'since ' in title and 'due ' in title
    assert 'Oct' in title and '2026' in title
    page.evaluate("REM.as_of = '2026-10-03T14:30:00Z'; render()", isolated_context=False)
    assert page.locator('.next-exchanges .when').first.inner_text() in ('due Oct 3', 'due 3 Oct')
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
    preview = page.locator('.lead-open')
    assert preview.locator('.dir').inner_text() == 'YOU OWE'
    assert preview.locator('.age').inner_text() == 'open for 5 days'
    assert len(preview.locator('.txt').inner_text()) <= 100
    assert 'exact due day still needs confirmation' in page.locator('.next-exchanges').inner_text()
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
      KNOWN.delete(r.path); render();
    }""", isolated_context=False)
    assert '1 day ago' in other.locator('.lead-meta').all_inner_texts()[-1]
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
    assert page.locator('.activity-day').all_inner_texts() == ['2026-09-04', '2026-09-03', '2026-09-02', '2026-09-01']
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
    assert page.locator('.focus-facts dt:text-is("Role") + dd').inner_text() == 'Programme manager (historical current unknown)'
    assert not page.locator('.focus-facts dt:text-is("Company")').count()
    page.evaluate("""() => {
      const r = REM.records.find(r => r.path === 'people/mara-ostrowski.md');
      r.text = r.text.replace(/^- Company:[^\\n]+\\n/m, '');
      KNOWN.delete(r.path); FACTS.delete(r.path); render();
    }""", isolated_context=False)
    assert page.locator('.focus-facts dt:text-is("Company") + dd').inner_text() == 'Old employer'


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
    dialog = page.locator('#evidence-dialog')
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
        dialog = page.locator('#evidence-dialog')
        find = dialog.get_by_role('searchbox', name='Find in archived source')
        assert find.is_visible()
        assert 'truncated' in dialog.inner_text().lower()
        original = dialog.locator('blockquote').inner_text()
        assert len(original) > 30000
        find.fill('Queue readback')
        assert dialog.locator('mark').inner_text() == 'Queue readback'
        assert 'Match 1 of 2' in dialog.locator('.evidence-find-status').inner_text()
        next_match = dialog.get_by_role('button', name='Next match')
        assert next_match.bounding_box()['height'] >= 44
        next_match.click()
        assert 'Match 2 of 2' in dialog.locator('.evidence-find-status').inner_text()
        assert dialog.locator('blockquote').inner_text() == original
        find.fill('not in this invented run')
        assert 'No match' in dialog.locator('.evidence-find-status').inner_text()
        assert not dialog.locator('mark').count()
        find.fill('.*')
        assert 'No match' in dialog.locator('.evidence-find-status').inner_text()
        find.fill('')
        assert dialog.locator('.evidence-find-status').inner_text() == ''
        assert dialog.locator('blockquote').inner_text() == original
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
    assert page.locator('.focus-head .focus-kicker').inner_text() == 'USEFUL FINDING'
    assert not page.locator('.focus-more').is_visible()
    finding_source = page.locator('.skill-finding-cites a.cite').first
    assert finding_source.get_attribute('href').endswith('h=src-1')
    assert finding_source.bounding_box()['width'] >= 44
    assert finding_source.bounding_box()['height'] >= 44
    finding_source.click()
    assert page.locator('#evidence-dialog blockquote').inner_text() == 'Recorded queue readback.'
    page.get_by_role('button', name='Close source context').click()
    assert finding_source.evaluate('e => e === document.activeElement')
    page.get_by_role('link', name='View sources →').click()
    assert page.locator('.deep-note .block-sources').is_visible()
    assert 'Use for a weekly brief.' in page.locator('.deep-note').inner_text()
    page.locator('.deep-note a.cite').first.click()
    assert page.locator('#evidence-dialog .evidence-summary').evaluate('e => e.scrollWidth <= e.clientWidth')
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
    assert 'SKILL-NAME MATCHES\n0' in page.locator('.focus-facts').inner_text()
    assert 'LAST ACTIVE' not in page.locator('.focus-facts').inner_text()
    assert 'LAST NAME MATCH' not in page.locator('.focus-facts').inner_text()
    assert 'last activity' not in page.locator('.eyebrow').inner_text()
    assert 'last name match' not in page.locator('.eyebrow').inner_text()
    assert 'file updated' in page.locator('.eyebrow').inner_text()
    page.goto(uri + '#r=skills%2Fcatalog%2Fweekly-brief.md')
    assert 'LAST NAME MATCH' in page.locator('.focus-facts').inner_text()
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
        assert 'SKILL-NAME MATCHES\n3' in page.locator('.focus-facts').inner_text()
        assert '3 skill-name matches' in page.locator('.lead-meta.usage').inner_text()
        assert 'retained eval attempts are counted separately' in page.locator('.usage-scope').inner_text()
        usage = page.locator('.panel').filter(has_text='Matched by skill name in coding sessions.')
        assert usage.is_visible()
        assert 'neither confirms this installed version or task outcome' in usage.inner_text()
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
        assert '— map date shown above' in page.locator(
            '.factlist dt:text-is("Last contact") + dd').inner_text()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        if width == 375:
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
    assert 'LAST MAPPED SESSION' in page.locator('.focus-facts').inner_text()
    assert 'last mapped session' in page.locator('.eyebrow').inner_text()
    assert 'Last active' not in page.locator('.leadrow').inner_text()
    page.goto(uri + '#c=projects')
    assert 'LAST MAPPED SESSION' in page.locator('.sheet thead').inner_text()


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
    page.get_by_role('button', name='Commitment 1', exact=True).click()
    assert not delivered.is_visible() and promised.is_visible()


def test_marked_sentence_with_a_markdown_link_and_code_respects_private_mode(reader):
    page, uri = reader
    page.goto(uri + '#r=people%2Fmara-ostrowski.md')
    page.evaluate(r"""() => {
      const r = byPath('people/mara-ostrowski.md');
      r.text += '\n\n## Private context\nPublic setup. [Quinn](quinn-alder.md) shared confidential details in `case.txt` [sensitive] [1]. Public follow-up.\n';
      KNOWN.delete(r.path); render();
    }""", isolated_context=False)
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
    monkeypatch.setattr(rem_reader, 'snapshot', lambda _: data)
    path = tmp_path / 'blocked.html'
    path.write_text(rem_reader.render(tmp_path / 'rem'))
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(path.as_uri())
    brief = page.locator('.morning')
    assert 'The last pass needs attention' in brief.inner_text()
    assert '2 investigations failed' in brief.inner_text()
    assert 'Model access was refused' in brief.inner_text()
    assert 'A request timed out' in brief.inner_text()
    assert 'private payload' not in brief.inner_text()
    assert 'No memory pages were written' in brief.inner_text()
    button = brief.get_by_role('button', name='Review failed runs →')
    assert button.bounding_box()['height'] >= 44
    button.focus()
    button.press('Enter')
    assert page.locator('details.maint').evaluate('(node) => node.open')
    assert page.locator('details.maint > summary').evaluate('(node) => node === document.activeElement')
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
    monkeypatch.setattr(rem_reader, 'snapshot', lambda _: data)
    path = tmp_path / 'partial.html'
    path.write_text(rem_reader.render(tmp_path / 'rem'))
    page.goto(path.as_uri())
    brief = page.locator('.morning')
    assert '1 investigation failed' in brief.inner_text()
    assert brief.locator('.memory-card').count() > 0
    assert 'No memory pages were written' not in brief.inner_text()
