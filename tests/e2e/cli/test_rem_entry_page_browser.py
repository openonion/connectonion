"""A knowledge entry, a decision and a principle read as one entry (#3097), in a real browser.

Opt in with CO_REM_BROWSER_TEST=1; needs installed Chrome. The notebook is invented: an entry in the older shape
(three sections, each with its own Sources), one in the shape the night writes now, a decision and a principle.
"""

import os
import re

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)

OLD = "knowledge/checking-a-tick.md"
OLD_TEXT = """# Checking a tick

- Also known as: Checking  a tick

A saved schedule does not show whether the job ran; only a receipt does. [1]
Mara said on 2026-02-03:
“The calendar trigger never fired.” [2]

## Drawn from
- [Trigger choice](../decisions/trigger-choice.md)
- [Receipts are written by the job](../decisions/receipts.md)

## Sources
- [1] codex:s1:12 — originating page: `decisions/trigger-choice.md`.
- [2] gmail:m1 — 2026-02-03 — Mara

## Receipts after the due time
Check the receipt after the due time, never the schedule. [1] The tick wrote one on the first night. [2]

### Drawn from
- [Receipts are written by the job](../decisions/receipts.md)

### Sources
- [1] codex:s3:7 — originating page: `decisions/receipts.md`
- [2] codex:s1:12 — originating page: `decisions/trigger-choice.md`.

## Retries stop after one
Retry once, then stop and say so. [1]

### Drawn from
- [Trigger choice](../decisions/trigger-choice.md)

### Sources
- [1] codex:s4:2 — originating page: `decisions/trigger-choice.md`
"""
NEW = "knowledge/plain-pages.md"
NEW_TEXT = """# Plain pages

Plain pages made diagnosis possible. [1]

## Drawn from
- [Trigger choice](../decisions/trigger-choice.md)
- [Receipts are written by the job](../decisions/receipts.md)

## Recovery
Search stayed linear and nobody minded. [2]

### Drawn from
- [Receipts are written by the job](../decisions/receipts.md)

## Sources
- [1] codex:s1:12 — originating page: `decisions/trigger-choice.md`.
- [2] codex:s3:7 — originating page: `decisions/receipts.md`.
"""
DECISION = "decisions/trigger-choice.md"
DECISION_TEXT = """# Trigger choice: a tick or a calendar

A tick. Chosen 2026-02-03:
“Use the interval tick.” [1]

## Why
The calendar trigger never fired in the trial.

## What it cost
A job can start up to a minute late.

## Sources
- [1] codex:s1:12 — owner, 2026-02-03; originating page: `sessions/trial.md`.
"""
PRINCIPLE = "principles/measure-the-behaviour.md"
PRINCIPLE_TEXT = """# Measure the behaviour

Pattern: twice the reported answer disagreed with what the system did.

Drawn from:
- [Trigger choice](../decisions/trigger-choice.md): the calendar said it was scheduled.
- [Receipts are written by the job](../decisions/receipts.md): the schedule said it ran.

Reach for it when a check would otherwise be "the API says it is fine".
"""


def notebook(root):
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    prepare(root)
    nb = Notebook(root)
    nb.write(OLD, OLD_TEXT)
    nb.write(NEW, NEW_TEXT)
    nb.write(DECISION, DECISION_TEXT)
    nb.write("decisions/receipts.md", "# Receipts are written by the job\n\nThe job writes it. “Write a receipt.” [1]\n\n"
             "## Why\nA schedule is a promise.\n\n## Sources\n- [1] codex:s3:7 — owner, 2026-02-04\n")
    nb.write(PRINCIPLE, PRINCIPLE_TEXT)
    return root


@pytest.fixture
def page(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem.reader import render
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    path = tmp_path / "reader.html"
    path.write_text(render(notebook(tmp_path / "rem"), local=True), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="en-US")
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url) if request.url.startswith("http") else None)
        page.route("http*://**/*", lambda route: route.abort())
        page.goto(path.as_uri())
        yield page, path.as_uri()
        browser.close()
        assert not errors, errors
        assert not requests, requests


def open_entry(page, uri, record):
    page.goto("about:blank")
    page.goto(uri + "#r=" + record.replace("/", "%2F"))
    page.locator(".entry h1").wait_for()
    return page.locator(".entry")


def test_the_entry_is_printed_once_and_sources_is_the_one_last_section(page):
    page, uri = page
    entry = open_entry(page, uri, OLD)
    text = page.locator("#main").inner_text()
    for sentence in ("only a receipt does", "The calendar trigger never fired", "never the schedule", "Retry once, then stop"):
        assert text.count(sentence) == 1, sentence
    assert page.locator("#main .deep-note").count() == 0
    assert page.locator("#main .entry-sources").count() == 1
    headings = entry.locator(".gx-main h2").all_inner_texts()
    assert [h.replace("#", "").strip() for h in headings] == ["Receipts after the due time", "Retries stop after one", "Sources"]
    # Nothing follows Sources in the reading column but the page's footer.
    assert page.evaluate("""() => { const s = document.querySelector('.entry-sources'); const next = s.nextElementSibling;
      return !!next && next.classList.contains('page-foot') && !next.nextElementSibling; }""")


def test_marks_run_on_and_link_to_their_note_and_back(page):
    page, uri = page
    entry = open_entry(page, uri, OLD)
    marks = entry.locator(".entry-text a.cite")
    assert marks.locator(".cite-number").all_inner_texts() == ["1", "2", "3", "1", "4"]
    notes = entry.locator(".entry-sources ol > li")
    assert notes.evaluate_all("items => items.map(li => li.id)") == ["src-1", "src-2", "src-3", "src-4"]
    assert marks.evaluate_all("marks => marks.map(a => new URLSearchParams(a.hash.slice(1)).get('h'))") == ["src-1", "src-2", "src-3", "src-1", "src-4"]
    # Each note links back to every mark that cites it, and the marks carry those ids.
    backs = notes.nth(0).locator("a.entry-back").evaluate_all("links => links.map(a => new URLSearchParams(a.hash.slice(1)).get('h'))")
    assert len(backs) == 2 and all(page.locator("#" + back).count() == 1 for back in backs)
    assert page.evaluate("ids => ids.every(id => document.getElementById(id).matches('.entry-text a.cite'))", backs)
    notes.nth(2).locator("a.entry-back").click()
    assert "h=ref-3" in page.url and page.locator("#ref-3").is_visible()


def test_a_note_says_what_the_source_is_in_words_and_keeps_the_identifier_out_of_sight(page):
    page, uri = page
    entry = open_entry(page, uri, OLD)
    notes = entry.locator(".entry-sources ol > li")
    shown = entry.locator(".entry-sources").inner_text()
    assert "Coding session" in notes.nth(0).inner_text() and "Mail" in notes.nth(1).inner_text()
    assert "codex:" not in shown and "gmail:" not in shown and "decisions/" not in shown
    assert "codex:s1:12" in notes.nth(0).get_attribute("title")
    entry.locator(".entry-sources .entry-ids").click()
    assert "codex:s1:12" in notes.nth(0).inner_text()


def test_drawn_from_is_once_per_section_as_links_and_apart_from_sources(page):
    page, uri = page
    entry = open_entry(page, uri, OLD)
    assert entry.locator(".entry-drawn").count() == 3
    first = entry.locator(".entry-sec").first.locator(".entry-drawn")
    assert first.locator(".entry-label").inner_text() == "Drawn from your notebook"
    assert first.locator("a").all_inner_texts() == ["Trigger choice", "Receipts are written by the job"]
    assert first.locator("a").first.get_attribute("href") == "#r=decisions%2Ftrigger-choice.md"
    assert entry.locator(".entry-sources .entry-drawn").count() == 0


def test_an_alias_equal_to_the_title_and_counters_at_zero_are_not_shown(page):
    page, uri = page
    entry = open_entry(page, uri, OLD)
    assert "Also known as" not in page.locator("#main").inner_text()
    assert entry.locator(".gx-stats, .entry-counts").count() == 0
    assert entry.locator(".toc").count() == 0  # two sections: no outline


def test_headings_have_more_room_above_than_below_and_the_text_has_room(page):
    page, uri = page
    entry = open_entry(page, uri, OLD)
    spacing = entry.locator(".entry-sec > h2").first.evaluate(
        "h => { const s = getComputedStyle(h); return [parseFloat(s.marginTop), parseFloat(s.marginBottom)]; }")
    assert spacing[0] >= 2 * spacing[1] and spacing[1] > 0
    body = entry.locator(".entry-text p").first.evaluate(
        "p => { const s = getComputedStyle(p); return [parseFloat(s.lineHeight) / parseFloat(s.fontSize), parseFloat(s.fontSize), p.getBoundingClientRect().width]; }")
    assert body[0] >= 1.7
    assert 30 * body[1] <= body[2] <= 52 * body[1]  # un-squeezed 3-column reading sheet (~740px on desktop, #3306)
    quote = entry.locator(".entry-text blockquote")
    assert quote.count() == 1 and "The calendar trigger never fired" in quote.inner_text()


def test_a_page_with_one_sources_section_keeps_its_numbers(page):
    page, uri = page
    entry = open_entry(page, uri, NEW)
    assert entry.locator(".entry-text a.cite .cite-number").all_inner_texts() == ["1", "2"]
    assert entry.locator(".entry-sources").count() == 1 and entry.locator(".entry-drawn").count() == 2
    assert page.locator("#main").inner_text().count("Search stayed linear") == 1


def test_a_decision_and_a_principle_follow_the_same_rules(page):
    page, uri = page
    entry = open_entry(page, uri, DECISION)
    text = page.locator("#main").inner_text()
    assert text.count("The calendar trigger never fired in the trial") == 1 and text.count("Use the interval tick") == 1
    assert page.locator("#main .deep-note").count() == 0
    headings = [h.replace("#", "").strip() for h in entry.locator(".gx-main h2").all_inner_texts()]
    assert headings == ["Why", "What it cost", "Sources"]
    assert "Coding session" in entry.locator(".entry-sources ol > li").inner_text()
    entry = open_entry(page, uri, PRINCIPLE)
    text = page.locator("#main").inner_text()
    assert text.count("twice the reported answer disagreed") == 1 and text.count("Reach for it when") == 1
    assert entry.locator(".entry-drawn a").all_inner_texts() == ["Trigger choice", "Receipts are written by the job"]
    assert "the calendar said it was scheduled" in entry.locator(".entry-drawn").inner_text()
    assert entry.locator(".entry-sources").count() == 0 and page.locator("#main .deep-note").count() == 0


def test_on_a_phone_the_side_column_folds_below_the_text(page):
    page, uri = page
    page.set_viewport_size({"width": 390, "height": 844})
    entry = open_entry(page, uri, OLD)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    tops = page.evaluate("""() => ['.entry-sources', '.page-nav .gx-rail'].map(s => document.querySelector('#main ' + s).getBoundingClientRect().top)""")
    assert tops[1] > tops[0]
    assert re.fullmatch(r"\d+(\.\d+)?px", entry.locator(".entry-text p").first.evaluate("p => getComputedStyle(p).fontSize"))
