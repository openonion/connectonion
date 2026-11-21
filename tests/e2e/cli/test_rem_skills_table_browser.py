"""Skills is the People table with family tabs and a few views (#3094), in a real browser (opt in).

The owner: the tabs are good, "but the table underneath is too overwhelming; do it like the People table; you
can add a few views." A tab shows one family and is in the address; a view re-orders the table in one click;
the finder filters within the current tab; on a phone a skill is two lines.

The notebook is the invented one in tests/fixtures/rem_reader_notebook.py with six more invented skills, so
there are families to tab between.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

FROZEN = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
ORDER = ["#", "#view=open", "#c=agenda", "#c=people", "#c=orgs", "#c=projects",
         "#c=knowledge", "#c=decisions", "#c=principles", "#c=skills",
         "#c=sessions", "#c=opportunities", "#c=works", "#view=changes"]
GROUP_STARTS = ["#c=people", "#c=knowledge", "#c=sessions"]
# name, matches, days since the last one, what it does
SKILLS = [("lark-im", 23, 2, "Send and read Lark messages."), ("lark-doc", 3, 30, "Read and edit Lark documents."),
          ("lark-base", 0, 0, "Work with Lark Base tables."), ("co-browser", 40, 5, "Drive one persistent browser."),
          ("co-mail", 5, 3, "Read and send mail."), ("co-env", 1, 100, "See and set keys in the env file.")]


def _notebook(tmp_path, full=True):
    from rem_reader_notebook import _skill, build
    from connectonion.rem.files import Notebook
    root = build(tmp_path / "rem", FROZEN)
    if not full:
        return root
    notebook, day = Notebook(root), lambda n: (FROZEN - timedelta(days=n)).date().isoformat()
    for name, count, last, what in SKILLS:
        notebook.write(f"skills/catalog/{name}.md", _skill(name, count, day(last), what, day(20)))
    for category in ("principles", "works", "opportunities", "sessions"):
        if not any((root / category).glob("*.md")):
            notebook.write(f"{category}/invented.md", f"# An invented {category} page\n\nOne line, so the place holds a page.\n")
    return root


def _open(tmp_path, monkeypatch, full=True):
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    snapshot = rem_reader.snapshot

    def fixed_snapshot(root, local=False, today=False):
        return {**snapshot(root, local, today=today), "as_of": FROZEN.isoformat()}

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    path = tmp_path / "reader.html"
    path.write_text(rem_reader.render(_notebook(tmp_path, full), local=True), encoding="utf-8")
    return path.as_uri()


@pytest.fixture
def browser():
    from patchright.sync_api import sync_playwright
    with sync_playwright() as api:
        chrome = api.chromium.launch(channel="chrome", headless=True)
        yield chrome
        chrome.close()


def _page(browser, uri, width, height, route="", phone=False):
    page = browser.new_page(viewport={"width": width, "height": height}, locale="en-US", is_mobile=phone, has_touch=phone)
    page.goto(uri + route)
    page.locator("#nav > a").first.wait_for(state="attached")
    return page


ROWS = "rows => rows.map(row => row.querySelector('.c-name').innerText.trim())"


def _skills(page):
    return page.locator(".skill-table tbody tr[data-href]").evaluate_all(ROWS)


def test_skills_is_one_table_with_most_used_first_and_no_cards(browser, tmp_path, monkeypatch):
    page = _page(browser, _open(tmp_path, monkeypatch), 1440, 900, "#c=skills")
    assert [text.strip().rstrip("↕↓↑").strip() for text in page.locator(".skill-table thead th").all_inner_texts()] == [
        "Skill", "What it does", "Family", "Last used", "Times used · 180 days"]
    assert _skills(page) == ["co-browser", "lark-im", "weekly-brief", "co-mail", "invoice-check", "lark-doc", "co-env", "lark-base", "talk-outline"]
    assert page.locator(".skill-card, .skill-cards, .skill-family").count() == 0
    first = page.locator(".skill-table tbody tr").first
    assert first.locator("td").all_inner_texts() == ["co-browser", "Drive one persistent browser", "co", "5 days ago", "40"]
    last = page.locator(".skill-table tbody tr").last.locator("td").all_inner_texts()
    assert last[3:] == ["Never", "0"]
    assert page.locator('.skill-table tbody tr:has-text("co-env") td.c-last').inner_text() == "3 months ago"
    heights = page.locator(".skill-table tbody tr").evaluate_all("rows => rows.map(row => row.getBoundingClientRect().height)")
    assert max(heights) <= 44  # one line a row, as People
    assert page.locator(".skill-table tbody tr").first.bounding_box()["y"] < 300  # the table starts in the first screen's top third
    assert page.locator(".skill-views [aria-current]").inner_text() == "Most used"
    first.locator("td.c-what").click()
    page.wait_for_function("location.hash.startsWith('#r=skills')")


def test_a_family_tab_filters_the_table_and_is_in_the_address(browser, tmp_path, monkeypatch):
    uri = _open(tmp_path, monkeypatch)
    page = _page(browser, uri, 1440, 900, "#c=skills")
    tabs = [" ".join(text.split()) for text in page.locator(".skill-tabs a").all_inner_texts()]
    assert tabs == ["All 9", "co 3", "Lark 3", "Other 3"]
    assert page.locator(".skill-tabs [aria-current]").inner_text().split() == ["All", "9"]
    page.locator(".skill-tabs a", has_text="Lark").click()
    page.wait_for_function("location.hash === '#c=skills&family=Lark'")
    assert _skills(page) == ["lark-im", "lark-doc", "lark-base"]
    assert page.locator(".skill-tabs [aria-current]").inner_text().split() == ["Lark", "3"]
    assert page.locator('#nav a[href="#c=skills"]').get_attribute("aria-current") == "page"  # still on Skills
    page.go_back()
    page.wait_for_function("location.hash === '#c=skills'")
    assert len(_skills(page)) == 9
    opened = _page(browser, uri, 1440, 900, "#c=skills&family=Other&v=recent")  # a bookmark opens the tab and the view
    assert _skills(opened) == ["weekly-brief", "invoice-check", "talk-outline"]
    assert opened.locator(".skill-views [aria-current]").inner_text() == "Recently used"


def test_the_views_reorder_the_table(browser, tmp_path, monkeypatch):
    page = _page(browser, _open(tmp_path, monkeypatch), 1440, 900, "#c=skills&family=Lark")
    page.locator(".skill-views a", has_text="Recently used").click()
    page.wait_for_function("location.hash === '#c=skills&family=Lark&v=recent'")  # the tab stays
    page.locator(".skill-tabs a", has_text="All").click()
    page.wait_for_function("location.hash === '#c=skills&v=recent'")
    assert _skills(page) == ["weekly-brief", "lark-im", "co-mail", "co-browser", "invoice-check", "lark-doc", "co-env", "lark-base", "talk-outline"]
    assert page.locator(".skill-table th.c-last").get_attribute("aria-sort") == "descending"
    page.locator(".skill-views a", has_text="By family").click()
    page.wait_for_function("location.hash === '#c=skills&v=family'")
    grouped = page.locator(".skill-table tbody tr").evaluate_all(
        "rows => rows.map(row => row.dataset.href ? row.querySelector('.c-name').innerText.trim() : '# ' + [...row.querySelector('th').childNodes].map(n => n.textContent).join(' '))")
    assert grouped == ["# co 3", "co-browser", "co-mail", "co-env", "# Lark 3", "lark-im", "lark-doc", "lark-base",
                       "# Other 3", "weekly-brief", "invoice-check", "talk-outline"]
    assert page.locator(".skill-table tbody th[scope=colgroup]").count() == 3
    page.locator(".skill-views a", has_text="Most used").click()
    page.wait_for_function("location.hash === '#c=skills'")
    assert _skills(page)[:2] == ["co-browser", "lark-im"]


def test_the_finder_filters_within_the_current_tab(browser, tmp_path, monkeypatch):
    page = _page(browser, _open(tmp_path, monkeypatch), 1440, 900, "#c=skills")
    find = page.locator(".skills-find")
    assert find.get_attribute("placeholder") == "Find among 9 skills…"
    find.fill("mail")
    assert _skills(page) == ["co-mail"]
    find.fill("read")
    assert _skills(page) == ["lark-im", "co-mail", "lark-doc"]
    page.locator(".skill-tabs a", has_text="Lark").click()
    page.wait_for_function("location.hash === '#c=skills&family=Lark'")
    assert page.locator(".skills-find").input_value() == "read"  # the words stay when the tab changes
    assert _skills(page) == ["lark-im", "lark-doc"]
    page.locator(".skills-find").fill("mail")
    assert _skills(page) == [] and "No matching pages" in page.locator(".people-empty").inner_text()
    page.locator(".people-empty a, .people-empty button").first.click()
    page.wait_for_function("location.hash === '#c=skills'")
    assert len(_skills(page)) == 9 and page.locator(".skills-find").input_value() == ""


def test_on_a_phone_the_tabs_are_one_row_and_a_skill_is_two_lines(browser, tmp_path, monkeypatch):
    page = _page(browser, _open(tmp_path, monkeypatch), 390, 844, "#c=skills", phone=True)
    tabs = page.locator(".skill-tabs a").evaluate_all("tabs => tabs.map(tab => Math.round(tab.getBoundingClientRect().top))")
    assert len(set(tabs)) == 1  # one row
    assert page.locator(".skill-tabs").evaluate("strip => getComputedStyle(strip).overflowX") == "auto"
    assert page.locator(".skill-tabs a").first.bounding_box()["height"] >= 44
    row = page.locator(".skill-table tbody tr").first.evaluate("""row => { const box = name => row.querySelector('.c-' + name).getBoundingClientRect();
      const shown = name => row.querySelector('.c-' + name).getClientRects().length > 0;
      return {nameFirst: box('name').top < box('what').top, sameLine: Math.abs(box('name').top - box('uses').top) < 12,
        metaRight: box('uses').left > box('name').right - 1 && box('last').left > box('name').left, lineBelow: box('what').top >= box('name').bottom - 1,
        family: shown('family'), height: row.getBoundingClientRect().height}; }""")
    assert row == {"nameFirst": True, "sameLine": True, "metaRight": True, "lineBelow": True, "family": False, "height": row["height"]}
    assert 44 <= row["height"] <= 80
    assert page.locator(".skill-table thead").evaluate("head => head.getClientRects().length") == 0
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
