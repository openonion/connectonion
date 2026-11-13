"""Agenda is a calendar of the owner's next days (#2998, asked in #2841; opt in).

Owner, 2026-11-13: «日程（Agenda）：我不是之前说过，日程 Agenda 要按照日历的形式来做吗？……我需要快速看到我最近
日历上有什么事件之类的，但完全没有啊！» At 1440 Agenda opens as a week grid from today, with the events the night
saved from his calendars beside the notebook's dated promises and agenda pages, each a link to its page or to
the calendar; a Month switch; on a phone, a day-by-day list. The notebook is the invented one in
tests/fixtures/rem_reader_notebook.py; the calendar is a fake saved through the night's own code path.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
FROZEN = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)  # a Thursday

GOOGLE = [
    {"id": "g1", "summary": "Pilot renewal call with Fernhill", "htmlLink": "https://calendar.example/g1",
     "start": {"dateTime": "2026-10-02T09:30:00Z"}, "end": {"dateTime": "2026-10-02T10:00:00Z"},
     "attendees": [{"email": "mara@fernhill.example"}]},
    {"id": "g2", "summary": "Harbour offsite", "htmlLink": "https://calendar.example/g2",
     "start": {"date": "2026-10-05"}, "end": {"date": "2026-10-07"}},
    {"id": "g3", "summary": "Dentist", "htmlLink": "https://calendar.example/g3",
     "start": {"dateTime": "2026-10-01T16:00:00Z"}, "end": {"dateTime": "2026-10-01T16:45:00Z"}},
    {"id": "g4", "summary": "Board dinner", "htmlLink": "https://calendar.example/g4",
     "start": {"dateTime": "2026-10-20T19:00:00Z"}, "end": {"dateTime": "2026-10-20T21:00:00Z"}},
]
OUTLOOK = [
    {"id": "o1", "subject": "Quarterly receipts with Ines", "webLink": "https://outlook.example/o1",
     "start": {"dateTime": "2026-10-01T08:00:00.0000000", "timeZone": "UTC"},
     "end": {"dateTime": "2026-10-01T08:30:00.0000000", "timeZone": "UTC"}},
]
FILING = """# Harbour filing

## Status
2026-09-28 — The Harbour return must be filed; due 2026-10-06 [1]

Sources: outlook:aa11 (2026-09-28)
"""


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from rem_reader_notebook import build
    from connectonion.rem import calendar, reader as rem_reader
    from connectonion.rem.files import Notebook
    from connectonion.rem.today import queue
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = build(tmp_path / "rem", FROZEN)
    Notebook(root).write("agenda/harbour-filing.md", FILING)
    monkeypatch.setattr(calendar, "available", lambda kind: True)
    monkeypatch.setattr(calendar, "calendar_events", lambda kind, start, end: GOOGLE if kind == "google" else OUTLOOK)
    calendar.save_upcoming(root, FROZEN)
    snapshot = rem_reader.snapshot

    def fixed_snapshot(root, local=False, today=False):
        data = snapshot(root, local, today=today)
        data["as_of"] = FROZEN.isoformat()
        data["status"]["timezone"] = "UTC"
        data["today_queue"] = queue(root, records=data["records"], contexts=data["source_context"],
                                    states=data["threads"], as_of=FROZEN.date())
        return data

    monkeypatch.setattr(rem_reader, "snapshot", fixed_snapshot)
    html = rem_reader.render(root, local=True)
    errors = []

    def serve(route):
        path = route.request.url[len(BASE) - 1:].split("#")[0]
        if path.startswith("/rem/"):
            return route.fulfill(status=200, body="{}", content_type="application/json")
        if path in ("/", "/index.html"):
            return route.fulfill(body=html, content_type="text/html")
        return route.abort()

    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US", reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        page.goto(BASE)
        page.locator(".night-card .count").wait_for()
        yield page
        browser.close()
    assert not errors, errors


def _open(page, width):
    page.set_viewport_size({"width": width, "height": 900 if width > 640 else 844})
    page.evaluate("() => { location.hash = '#c=agenda'; }", isolated_context=False)
    page.locator(".agenda").wait_for()


def _days(page, selector):
    return page.locator(selector).evaluate_all("cols => cols.map(c => c.innerText.trim())")


def test_agenda_opens_as_this_weeks_grid_with_calendar_events_and_notebook_dates(agenda):
    page = agenda
    _open(page, 1440)
    week = page.locator(".agenda-week")
    assert week.is_visible() and not page.locator(".agenda-days").is_visible()
    # No title and no explanation first: the week is the first thing on the page.
    main = page.locator("#main").inner_text()
    assert "promises, waiting on others" not in main
    assert week.bounding_box()["y"] < 140
    days = _days(page, ".agenda-week .ag-col")
    assert len(days) == 7
    assert days[0].startswith("Today\nThu 1"), days[0]
    assert days[1].startswith("Fri 2") and days[6].startswith("Wed 7")
    # Today, in time order: the Outlook meeting, then the Google one.
    assert "08:00\nQuarterly receipts with Ines" in days[0] and "16:00\nDentist" in days[0]
    assert days[0].index("Quarterly receipts") < days[0].index("Dentist")
    assert "09:30\nPilot renewal call with Fernhill" in days[1]
    # An all-day event spans its days; Google's end date is the day after.
    assert "Harbour offsite" in days[4] and "Harbour offsite" in days[5] and "Harbour offsite" not in days[6]
    # The notebook's own dates: Ines's promise due 3 Oct, the agenda page due 6 Oct.
    assert "Inès Halvorsen" in days[2]
    assert "Harbour filing" in days[5]
    assert "Board dinner" not in week.inner_text(), "outside this week"
    # Every item links: an event to the calendar it came from, a promise or page to its notebook page.
    event = week.get_by_role("link", name="Pilot renewal call with Fernhill")
    assert event.get_attribute("href") == "https://calendar.example/g1" and event.get_attribute("target") == "_blank"
    person = page.locator(".agenda-week .ag-col").nth(1).get_by_role("link", name="Mara Ostrowski")
    assert person.get_attribute("href") == "#r=people%2Fmara-ostrowski.md"
    filing = week.get_by_role("link", name="Harbour filing")
    filing.click()
    page.wait_for_function("() => location.hash === '#r=agenda%2Fharbour-filing.md'")
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")


def test_the_week_moves_and_month_shows_the_whole_month(agenda):
    page = agenda
    _open(page, 1440)
    page.get_by_role("button", name="Next week").click()
    assert page.locator(".agenda-week .ag-col").first.inner_text().startswith("Thu 8")
    page.get_by_role("button", name="Today", exact=True).click()
    assert page.locator(".agenda-week .ag-col").first.inner_text().startswith("Today")
    page.get_by_role("button", name="Month", exact=True).click()
    month = page.locator(".agenda-month")
    assert month.is_visible() and not page.locator(".agenda-week").is_visible()
    assert "October 2026" in page.locator(".agenda-bar").inner_text()
    cells = page.locator(".agenda-month .ag-cell")
    assert cells.count() in (35, 42)
    assert cells.first.inner_text().startswith("28"), "a Monday-first grid opens on 28 September"
    assert "Board dinner" in month.inner_text() and "Pilot renewal call with Fernhill" in month.inner_text()
    assert page.locator(".agenda-month .ag-cell.today").inner_text().startswith("1")
    page.get_by_role("button", name="Week", exact=True).click()
    assert page.locator(".agenda-week").is_visible()


def test_a_phone_gets_a_day_by_day_list(agenda):
    page = agenda
    _open(page, 390)
    days = page.locator(".agenda-days")
    assert days.is_visible() and not page.locator(".agenda-week").is_visible()
    heads = page.locator(".agenda-days .ag-dayhead").all_inner_texts()
    assert heads[:3] == ["Today · Thu 1 Oct", "Tomorrow · Fri 2 Oct", "Sat 3 Oct"], heads
    first = page.locator(".agenda-days .ag-day").first.inner_text()
    assert first.index("Quarterly receipts with Ines") < first.index("Dentist")
    assert "Harbour offsite" in days.inner_text() and "Board dinner" in days.inner_text()
    # The first thing on the phone is today's first event, not a heading or a toggle.
    assert page.locator(".agenda-days .ag-item").first.bounding_box()["y"] < 260
    assert not page.get_by_role("button", name="Month", exact=True).is_visible()
    assert page.locator(".agenda-days .ag-item a").first.bounding_box()["height"] >= 44
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")


def test_chinese_and_a_calendar_not_yet_read(agenda):
    page = agenda
    _open(page, 1440)
    page.evaluate("() => setInterfaceLanguage('zh')", isolated_context=False)
    assert page.locator(".agenda-week .ag-col").first.inner_text().startswith("今天\n周四 1")
    assert page.get_by_role("button", name="月", exact=True).is_visible()
    page.evaluate("() => { setInterfaceLanguage('en'); REM.calendar = null; render(); }", isolated_context=False)
    note = page.locator(".agenda-note").inner_text()
    assert note == "No calendar read yet: REM reads your connected Google and Outlook calendars each night."
    # The notebook's dates still fill the week.
    assert "Inès Halvorsen" in page.locator(".agenda-week").inner_text()
    page.evaluate("""() => { REM.calendar = {saved_at: '2026-10-01T02:00:00+00:00', read: ['Google Calendar'],
      errors: {Outlook: 'authorization expired'}, events: []}; render(); }""", isolated_context=False)
    note = page.locator(".agenda-note").inner_text()
    assert note == "Outlook could not be read last night (authorization expired)."
    assert "co auth" not in page.locator("#main").inner_text()
