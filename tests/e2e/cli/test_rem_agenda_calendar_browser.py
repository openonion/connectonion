"""Agenda is a calendar of the owner's next days (#2998, asked in #2841; opt in).

Owner, 2026-11-13: «日程（Agenda）：我不是之前说过，日程 Agenda 要按照日历的形式来做吗？……我需要快速看到我最近
日历上有什么事件之类的，但完全没有啊！» Owner, 2026-11-17: «The Agenda does not look like a calendar at all. There is
a week/month switch, but it does not look like a calendar… show it with that kind of very fine, precise calendar.»
So the week is a time grid from today (hours on a quiet axis, events as blocks placed by start and sized by
length, overlaps side by side, an all-day strip, a now line) and the month a grid of weeks; on a phone a strip
of dates over a day-by-day list. The notebook is the invented one in tests/fixtures/rem_reader_notebook.py; the
calendar is the invented week in tests/fixtures/rem_calendar_week.py, saved through the night's own code path.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))
from rem_calendar_week import ALL_OWN, FILING, FROZEN, GOOGLE, INVOICE, LISTED, OUTLOOK  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
TODOS = [
    {"id": "t1", "title": "Order lantern glass", "status": "notStarted", "_list": "Workshop"},
    {"id": "t2", "title": "Renew the harbour permit", "status": "notStarted", "_list": "Tasks",
     "dueDateTime": {"dateTime": "2026-10-06T00:00:00.0000000", "timeZone": "UTC"}},
    {"id": "t3", "title": "Post the old invoice", "status": "inProgress", "_list": "Tasks",
     "dueDateTime": {"dateTime": "2026-09-24T00:00:00.0000000", "timeZone": "UTC"}},
    {"id": "t4", "title": "Already done", "status": "completed", "_list": "Tasks"},
]

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
    Notebook(root).write("agenda/fernhill-invoice.md", INVOICE)
    monkeypatch.setattr(calendar, "available", lambda kind: True)
    monkeypatch.setattr(calendar, "calendar_events", lambda kind, start, end, zone: (GOOGLE, LISTED) if kind == "google" else (OUTLOOK, ALL_OWN))
    calendar.save_upcoming(root, FROZEN)
    from rem_calendar_week import seed_weather
    from connectonion.rem import weather
    seed_weather(root, weather)  # an invented forecast for the first five days, saved by the night's own code
    # His open to-dos, read in the same step of the night (#3087): Graph's own task objects, invented.
    from connectonion.rem import todos
    monkeypatch.setattr(todos, "available", lambda: True)
    monkeypatch.setattr(todos, "google_tasks", lambda: "reconnect")
    monkeypatch.setattr(todos, "todo_tasks", lambda zone: TODOS)
    todos.save(root, FROZEN)
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


def _box(page, selector, text=None):
    found = page.locator(selector, has_text=text) if text else page.locator(selector)
    return found.first.bounding_box()


def _column(page, day):
    return page.locator(f'.cal-day[data-day="2026-10-{day:02d}"]')


def _night(tmp_path, monkeypatch, connected, failing=None):
    """What the reader gets from the file a night writes: `connected` calendars, `failing` raising its error."""
    from connectonion.rem import calendar

    nights = []

    def events(kind, start, end, zone):
        if failing and kind == failing[0] and len(nights) > 1:
            raise failing[1]
        return (GOOGLE, LISTED) if kind == "google" else (OUTLOOK, ALL_OWN)

    root = tmp_path / "night"
    monkeypatch.setattr(calendar, "available", lambda kind: kind in connected)
    monkeypatch.setattr(calendar, "calendar_events", events)
    # A good night ten days ago, then (when one fails) tonight.
    for moment in [FROZEN - timedelta(days=10), FROZEN][: 2 if failing else 1]:
        nights.append(moment)
        calendar.save_upcoming(root, moment)
    return calendar.upcoming(root, [], "")


def test_agenda_opens_as_this_weeks_time_grid_with_calendar_events_and_notebook_dates(agenda):
    page = agenda
    _open(page, 1440)
    week = page.locator(".cal-week")
    assert week.is_visible() and not page.locator(".cal-phone").is_visible()
    # No title and no explanation first: the bar, one small line of provenance, then the week.
    assert "promises, waiting on others" not in page.locator("#main").inner_text()
    assert week.bounding_box()["y"] < 180
    heads = page.locator(".cal-heads .cal-head").all_inner_texts()
    assert len(heads) == 7
    # The week starts today; today's head is marked and says so.
    assert "Today" in heads[0] and "Thu" in heads[0] and "Today" not in "".join(heads[1:])
    assert page.locator(".cal-head.today .cal-num").inner_text() == "1"
    # Today, placed by time: the Outlook meeting above the Google one.
    today = _column(page, 1)
    assert _box(today, ".cal-ev", "Quarterly receipts with Ines")["y"] < _box(today, ".cal-ev", "Dentist")["y"]
    assert "09:30 – 10:00" in _column(page, 2).locator(".cal-ev", has_text="Pilot renewal call with Fernhill").get_attribute("title")
    # The notebook's own dates are counted in the all-day strip, one quiet line per day (#3188): Inès's promise due
    # 3 Oct, the agenda page due 6 Oct; the items themselves are Today's cards.
    strip = page.locator(".cal-allday")
    assert strip.locator('.cal-due-count[title*="Inès Halvorsen"]').count() == 1 and strip.locator('.cal-due-count[title*="Harbour filing"]').count() == 1
    assert strip.locator(".cal-bar", has_text="Inès Halvorsen").count() == 0
    assert "Board dinner" not in week.inner_text(), "outside this week"
    # An empty day is empty: no placeholder card and no dash.
    assert page.locator(".cal-week .ag-empty").count() == 0 and "—" not in _column(page, 4).inner_text()
    # #3152: the week is opened inside Today, scrolled into view; the hours scroll inside the grid, under the heads.
    assert page.evaluate("() => { const b = document.getElementById('today-calendar').getBoundingClientRect(); return b.top >= -1 && b.top < innerHeight / 2; }")
    assert page.evaluate("() => { const s = document.querySelector('.agenda .cal-scroll'); return s.scrollHeight > s.clientHeight; }")
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")


def test_an_event_opens_its_detail_in_words_and_a_notebook_date_goes_to_its_page(agenda):
    page = agenda
    _open(page, 1440)
    block = _column(page, 2).get_by_role("button", name="Pilot renewal call with Fernhill")
    # Which calendar it is from is said in words on hover, not by the edge's shade alone.
    assert "Google Calendar" in block.get_attribute("title")
    assert "Outlook" in _column(page, 1).get_by_role("button", name="Standup").get_attribute("title")
    block.click()
    detail = page.locator("dialog.cal-detail")
    assert detail.locator("h2").inner_text() == "Pilot renewal call with Fernhill"
    text = detail.inner_text()
    assert "Fri" in text and "2 Oct" in text and "09:30 – 10:00" in text and "Fernhill Labs, Room 2" in text and "In Google Calendar" in text
    link = detail.get_by_role("link", name="Open in Google Calendar")
    assert link.get_attribute("href") == "https://calendar.example/g1" and link.get_attribute("target") == "_blank"
    assert detail.get_by_role("link", name="Mara Ostrowski").get_attribute("href") == "#r=people%2Fmara-ostrowski.md"
    box = detail.bounding_box()
    assert 0 <= box["x"] and box["x"] + box["width"] <= 1440 and 0 <= box["y"] and box["y"] + box["height"] <= 900
    page.keyboard.press("Escape")
    detail.wait_for(state="detached", timeout=3000)  # it closes on Escape; counted at once it can still be leaving
    page.locator('.cal-allday .cal-due-count[title*="Harbour filing"]').click()  # one date: its count opens its page
    page.wait_for_function("() => location.hash === '#r=agenda%2Fharbour-filing.md'")


def test_a_block_is_as_tall_as_its_minutes_and_overlapping_events_stand_side_by_side(agenda):
    page = agenda
    _open(page, 1440)
    hour = page.evaluate("() => { const hours = [...document.querySelectorAll('.cal-hour:not(.cal-now-word)')]; return hours[1].getBoundingClientRect().top - hours[0].getBoundingClientRect().top; }")
    day = _column(page, 2)
    review, call, renewal = (_box(day, ".cal-ev", name) for name in ("Design review", "Supplier call", "Pilot renewal call"))
    column = day.bounding_box()
    # A 90-minute event is one and a half hour-rows tall, and starts an hour and a half... at its start.
    assert abs(review["height"] - 1.5 * hour) <= 2, (review, hour)
    assert abs((review["y"] - renewal["y"]) - 0.5 * hour) <= 2, "10:00 is half an hour under 09:30"
    # Two that overlap share the column side by side; neither covers the other.
    assert review["x"] + review["width"] <= call["x"] + 1 and call["y"] < review["y"] + review["height"] and call["y"] > review["y"]
    assert call["x"] + call["width"] <= column["x"] + column["width"] + 1
    # Back to back is not an overlap: the 09:30 call keeps the whole column.
    assert renewal["width"] > 0.85 * column["width"] and renewal["y"] + renewal["height"] <= review["y"] + 1
    # A quarter-hour event still shows its title.
    standup = _column(page, 1).locator(".cal-ev", has_text="Standup")
    assert standup.locator(".cal-ev-title").is_visible() and standup.bounding_box()["height"] >= 18
    # A tall block says its time and its place under its title.
    assert day.locator(".cal-ev", has_text="Design review").locator(".cal-ev-where").is_visible()


def test_a_three_day_all_day_event_is_one_bar_across_its_days(agenda):
    page = agenda
    _open(page, 1440)
    bars = page.locator(".cal-allday .cal-bar", has_text="Harbour offsite")
    assert bars.count() == 1
    bar, first, last = bars.bounding_box(), _column(page, 5).bounding_box(), _column(page, 7).bounding_box()
    assert first["x"] <= bar["x"] <= first["x"] + 8 and last["x"] + last["width"] - 8 <= bar["x"] + bar["width"] <= last["x"] + last["width"]
    assert page.locator(".cal-day .cal-ev", has_text="Harbour offsite").count() == 0, "not a block in the hours"
    assert "All day" in bars.get_attribute("title") and "5 Oct" in bars.get_attribute("title") and "7 Oct" in bars.get_attribute("title")
    # A single all-day event is a bar one day wide.
    kiln = _box(page, ".cal-allday .cal-bar", "Kiln firing day")
    assert kiln["width"] <= _column(page, 3).bounding_box()["width"]


def test_a_timed_event_over_several_days_is_one_bar_in_the_strip_not_a_block_from_midnight(agenda):
    """Seen on the owner's notebook: an event from one afternoon to a morning two days on filled each of its days
    as a block from midnight, its title scrolled out of sight. A calendar puts it in the all-day strip."""
    page = agenda
    _open(page, 1440)
    bars = page.locator(".cal-allday .cal-bar", has_text="Coast walk")
    assert bars.count() == 1
    first, last = page.locator('.cal-day[data-day="2026-10-05"]').bounding_box(), page.locator('.cal-day[data-day="2026-10-07"]').bounding_box()
    bar = bars.bounding_box()
    assert first["x"] <= bar["x"] <= first["x"] + 8 and last["x"] + last["width"] - 8 <= bar["x"] + bar["width"] <= last["x"] + last["width"]
    assert page.locator(".cal-day .cal-ev", has_text="Coast walk").count() == 0, "not a block in the hours"
    said = bars.get_attribute("title")
    assert "All day" not in said and "5 Oct" in said and "14:00" in said and "7 Oct" in said and "11:00" in said, said
    page.get_by_role("button", name="Month", exact=True).click()
    assert page.locator(".cal-month .cal-bar", has_text="Coast walk").count() >= 1
    assert page.locator(".cal-month .cal-line", has_text="Coast walk").count() == 0


def test_the_now_line_is_on_today_only_and_the_axis_says_the_time(agenda):
    page = agenda
    _open(page, 1440)
    assert page.locator(".cal-now").count() == 1 and _column(page, 1).locator(".cal-now").count() == 1
    assert page.locator(".cal-now-word").inner_text() == "Now 12:00"
    lunch, now = _box(_column(page, 1), ".cal-ev", "Lunch with Mara"), page.locator(".cal-now").bounding_box()
    assert now["y"] < lunch["y"], "12:00 is above the 12:30 lunch"
    # The grid opens so the first event of the week (05:30) and now are both in view.
    scroll = page.locator(".cal-scroll").bounding_box()
    for box in (_box(_column(page, 2), ".cal-ev", "Dawn tide check"), now):
        assert scroll["y"] <= box["y"] and box["y"] + box["height"] <= scroll["y"] + scroll["height"]
    page.get_by_role("button", name="Next week").click()
    assert page.locator(".cal-now").count() == 0 and page.locator(".cal-now-word").count() == 0
    # An empty week opens on working hours: 07:00 to 20:00 are on screen without scrolling.
    scroll = page.locator(".cal-scroll").bounding_box()
    for clock in ("07:00", "20:00"):
        box = page.locator(".cal-hour", has_text=clock).bounding_box()
        assert scroll["y"] <= box["y"] + box["height"] and box["y"] + box["height"] <= scroll["y"] + scroll["height"], clock


def test_a_late_notebook_date_is_on_today_saying_when_it_was_due_and_no_second_list_sits_under_the_calendar(agenda):
    page = agenda
    _open(page, 1440)
    assert page.locator(".agenda-earlier").count() == 0
    late = page.locator('.cal-allday .cal-due-count.late[title*="Fernhill invoice"]')  # counted on today, in red
    assert "Late, due Sep 25" in late.get_attribute("title")
    first = _column(page, 1).bounding_box()
    assert first["x"] <= late.bounding_box()["x"] <= first["x"] + first["width"]
    page.get_by_role("button", name="Next week").click()
    assert page.locator('.cal-due-count[title*="Fernhill invoice"]').count() == 0


def test_the_week_moves_and_month_is_a_grid_of_weeks_with_bars_across_cells(agenda):
    page = agenda
    _open(page, 1440)
    page.get_by_role("button", name="Next week").click()
    first = page.locator(".cal-heads .cal-head").first.inner_text()
    assert "Today" not in first and "8" in first
    page.get_by_role("button", name="Today", exact=True).click()
    assert "Today" in page.locator(".cal-heads .cal-head").first.inner_text()
    page.get_by_role("button", name="Month", exact=True).click()
    month = page.locator(".cal-month")
    assert month.is_visible() and page.locator(".cal-week").count() == 0
    assert "October 2026" in page.locator(".agenda-bar").inner_text()
    cells = page.locator(".cal-month .cal-cell")
    assert cells.count() in (35, 42)
    assert cells.first.locator(".cal-num").inner_text() == "28", "a Monday-first grid opens on 28 September"
    assert "out" in cells.first.get_attribute("class"), "a day outside the month is dimmed"
    today = page.locator(".cal-month .cal-cell.today")
    assert today.locator(".cal-num").inner_text() == "1" and "Today" in today.inner_text()
    # A line is its time and its title; a three-day event is one bar across three cells of its week.
    assert page.locator(".cal-line", has_text="Board dinner").inner_text().split() == ["19:00", "Board", "dinner"]
    bars = page.locator(".cal-month .cal-bar", has_text="Harbour offsite")
    assert bars.count() == 1
    bar, cell = bars.bounding_box(), page.locator('.cal-cell[data-day="2026-10-05"]').bounding_box()
    assert 2.7 * cell["width"] <= bar["width"] <= 3 * cell["width"] and cell["x"] <= bar["x"] <= cell["x"] + 8
    # Up to three lines in a cell; the rest is counted in words, and the count opens that day.
    day = page.locator('.cal-cell[data-day="2026-10-02"]').bounding_box()
    lines = page.locator(".cal-line").evaluate_all("(lines, x) => lines.filter(line => Math.abs(line.getBoundingClientRect().x - x) < 12).map(line => line.innerText.replace(/\\s+/g, ' '))", day["x"])
    assert lines == ["05:30 Dawn tide check", "09:30 Pilot renewal call with Fernhill", "10:00 Design review"]
    more = page.get_by_role("button", name="+1 more")
    assert abs(more.bounding_box()["x"] - day["x"]) < 12
    more.click()
    assert page.locator(".cal-week").is_visible() and "Fri" in page.locator(".cal-heads .cal-head").first.inner_text()
    assert "Supplier call" in _column(page, 2).inner_text()
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")


def test_arrows_move_the_day_t_is_today_and_enter_opens(agenda):
    page = agenda
    _open(page, 1440)
    # On Today the arrows belong to the calendar only while it has the focus (#3152), never to the cards above.
    page.keyboard.press("ArrowRight")
    assert page.locator(".cal-head.sel").count() == 0
    page.locator(".agenda .cal-scroll").focus()
    page.keyboard.press("ArrowRight")
    assert page.locator(".cal-head.sel").get_attribute("data-day") == "2026-10-02"
    page.keyboard.press("Enter")
    assert page.locator("dialog.cal-detail h2").inner_text() == "Dawn tide check"
    page.keyboard.press("Escape")
    page.keyboard.press("ArrowDown")
    assert page.locator(".cal-head.sel").get_attribute("data-day") == "2026-10-09"
    assert "8" in page.locator(".cal-heads .cal-head").first.inner_text(), "the week followed the chosen day"
    page.keyboard.press("t")
    assert "Today" in page.locator(".cal-heads .cal-head").first.inner_text()
    assert page.locator(".cal-head.sel").get_attribute("data-day") == "2026-10-01"


def test_a_phone_gets_a_strip_of_dates_over_a_day_by_day_list(agenda):
    page = agenda
    _open(page, 390)
    days = page.locator(".cal-phone .agenda-days")
    assert days.is_visible() and not page.locator(".cal-week").is_visible()
    strip = page.locator(".cal-strip .cal-jump")
    assert strip.count() == 7 and strip.first.get_attribute("aria-label").endswith("5 items")
    assert strip.locator(".cal-num").all_inner_texts() == ["1", "2", "3", "4", "5", "6", "7"]
    heads = page.locator(".agenda-days .ag-dayhead").all_inner_texts()
    assert "Today" in heads[0] and "Tomorrow" in heads[1] and "Sat" in heads[2], heads
    assert not any("Sun" in head for head in heads[:4]), "a day with nothing has no section"
    assert strip.nth(3).is_disabled()
    first = page.locator(".agenda-days .ag-day").first.inner_text()
    assert first.index("Quarterly receipts with Ines") < first.index("Dentist")
    # A three-day event is listed once, with its range in words.
    assert days.locator(".cal-row", has_text="Harbour offsite").count() == 1
    offsite = days.locator(".cal-row", has_text="Harbour offsite").inner_text()
    assert "All day" in offsite and "5 Oct" in offsite and "7 Oct" in offsite
    assert "Board dinner" in days.inner_text()
    # The first event is on the first screen; a row is a thumb's height.
    assert page.locator(".agenda-days .cal-row").first.bounding_box()["y"] < 360
    assert page.locator(".agenda-days .cal-row").evaluate_all("rows => rows.every(row => row.getBoundingClientRect().height >= 44)")
    # A date in the strip jumps to its day.
    strip.nth(1).click()
    page.wait_for_timeout(200)
    assert abs(page.locator("#cal-day-2026-10-02").bounding_box()["y"]) < 80
    # An event opens as a sheet from the foot.
    page.evaluate("() => scrollTo(0, 0)")
    page.locator(".agenda-days .cal-row", has_text="Dentist").click()
    sheet = page.locator("dialog.cal-detail.n3-sheet")
    assert "16:00 – 16:45" in sheet.inner_text() and "In Google Calendar" in sheet.inner_text()
    sheet.get_by_role("button", name="Close").click()
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")


def test_a_phones_month_is_the_grid_with_a_count_in_each_cell_and_the_tapped_days_list_under_it(agenda):
    page = agenda
    _open(page, 390)
    page.get_by_role("button", name="Month", exact=True).click()
    assert page.locator(".cal-month .cal-cell").count() in (35, 42)
    assert page.locator(".cal-month .cal-line, .cal-month .cal-bar").evaluate_all("nodes => nodes.every(node => !node.offsetParent)")
    cell = page.locator('.cal-cell[data-day="2026-10-02"]')
    assert cell.locator(".cal-count").inner_text() == "4" and cell.get_attribute("aria-label").endswith("4 items")
    assert page.locator('.cal-cell[data-day="2026-10-04"] .cal-count').count() == 0
    # Today's list is under the grid until another day is tapped.
    assert "Dentist" in page.locator(".cal-daylist").inner_text()
    cell.click()
    listed = page.locator(".cal-daylist")
    assert "Fri" in listed.locator(".ag-dayhead").inner_text()
    assert listed.locator(".cal-row-title").all_inner_texts() == ["Dawn tide check", "Pilot renewal call with Fernhill", "Design review", "Supplier call"]
    grid, tabbar = page.locator(".cal-month .cal-mweek").last.bounding_box(), page.locator("#tabbar").bounding_box()
    assert grid["y"] + grid["height"] <= tabbar["y"], "the whole grid is above the tab bar"
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")


def test_chinese(agenda):
    page = agenda
    _open(page, 1440)
    page.evaluate("() => setInterfaceLanguage('zh')", isolated_context=False)
    assert "今天" in page.locator(".cal-heads .cal-head").first.inner_text()
    assert page.get_by_role("button", name="月", exact=True).is_visible()
    assert page.locator(".cal-now-word").inner_text() == "现在 12:00"
    page.evaluate("() => setInterfaceLanguage('en')", isolated_context=False)


@pytest.mark.parametrize("width", [1440, 390])
def test_agenda_says_in_words_which_calendars_it_read_and_which_it_left_out(agenda, width):
    """Owner, 2026-11-17 (#3087): other people's entries were on his day. Only his own calendars are read, and the page says so."""
    page = agenda
    _open(page, width)
    note = page.locator(".agenda-read").inner_text()
    # Small, under the header, above the calendar on a desk and on a phone.
    body = page.locator(".cal-week" if width > 640 else ".cal-phone").bounding_box()
    read = page.locator(".agenda-read").bounding_box()
    assert read["y"] + read["height"] <= body["y"] and page.locator(".agenda-read").evaluate("node => getComputedStyle(node).fontSize") == "11px"
    assert "Google Calendar: 1 own calendar read; 3 left out (2 shared as free/busy, 1 shared read-only)." in note
    assert "Outlook: 2 own calendars read; none left out." in note
    page.evaluate("() => setInterfaceLanguage('zh')", isolated_context=False)
    note = page.locator(".agenda-read").inner_text()
    assert "Google Calendar：读了 1 个自己的日历；3 个没有读（2 个只共享忙闲，1 个只读共享）。" in note
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_today_shows_his_to_dos_in_their_own_section_in_words(agenda, width):
    """Owner, 2026-11-17 (#3087): none of his to-dos were on Today. They are, apart from events, each named a to-do."""
    page = agenda
    page.set_viewport_size({"width": width, "height": 900 if width > 640 else 844})
    page.evaluate("() => { location.hash = '#'; }", isolated_context=False)
    section = page.locator("section.todos")
    section.wait_for()
    assert section.get_attribute("aria-label") == section.locator("h2").inner_text() == "To-dos"
    rows = [" | ".join(line for line in text.split("\n") if line) for text in section.locator("li").all_inner_texts()]
    assert rows == ["To-do — overdue since Sep 24 | Post the old invoice | List: Tasks",
                    "To-do — due Oct 6 | Renew the harbour permit | List: Tasks",
                    "To-do — no due date | Order lantern glass | List: Workshop"]
    assert "Google Tasks are not read: Google must be reconnected with access to tasks." in section.inner_text()
    # Read, not acted on: a to-do is ticked off in Microsoft To Do, so the section has no button and no command.
    assert section.locator("button, input, code").count() == 0 and "co auth" not in section.inner_text()
    # Events stay in Your day; no to-do is listed among them.
    assert page.locator("section.day-plan:not(.todos)").count() <= 1
    assert "Post the old invoice" not in page.locator("section.day-plan:not(.todos)").all_inner_texts().__str__()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.evaluate("() => setInterfaceLanguage('zh')", isolated_context=False)
    assert "待办 — 没有期限" in section.inner_text()
    page.evaluate("() => setInterfaceLanguage('en')", isolated_context=False)


def _show(page, shown):
    page.evaluate("shown => { REM.calendar = shown; render(); }", shown, isolated_context=False)
    note = page.locator(".agenda-note:not(.agenda-read)")
    return note.inner_text() if note.count() else ""


def test_before_any_night_and_with_no_calendar_connected_the_page_says_so(agenda, tmp_path, monkeypatch):
    page = agenda
    _open(page, 1440)
    assert "No calendar read yet" in _show(page, None)
    # The file a night writes when co can read no calendar: not an unexplained empty week.
    note = _show(page, _night(tmp_path, monkeypatch, connected=()))
    assert "No calendar is connected" in note
    assert page.locator('.cal-week .cal-due-count[title*="Inès Halvorsen"]').count() == 1, "the notebook's dates are still counted in the week"
    assert "co auth" not in page.locator("#main").inner_text()


def test_a_calendar_that_failed_says_when_and_why_and_how_old_its_events_are(agenda, tmp_path, monkeypatch):
    from connectonion.provider_credentials import ProviderCredentialError
    page = agenda
    _open(page, 1440)
    expired = ProviderCredentialError("reauth_required", "Microsoft authorization expired.", "co auth microsoft")
    note = _show(page, _night(tmp_path, monkeypatch, connected=("google", "microsoft"), failing=("microsoft", expired)))
    assert "Outlook could not be read" in note and "authorization expired" in note and "Today" in note
    assert "Its events are from" in note and "Sep 21" in note
    assert "last night" not in note and "co auth" not in page.locator("#main").inner_text()
    # Its earlier events are still on the week.
    assert "Quarterly receipts with Ines" in page.locator(".cal-week").inner_text()
    note = _show(page, _night(tmp_path / "bug", monkeypatch, connected=("google",), failing=("google", AttributeError("x"))))
    assert "a fault in REM" in note and "AttributeError" in note and "Traceback" not in note
    shown = _night(tmp_path / "cap", monkeypatch, connected=("google",))
    shown["read"][0]["capped"] = 1000
    note = _show(page, shown)
    assert "Google Calendar has more than 1000 events in these weeks; REM kept the first 1000 and skipped the rest." in note


@pytest.mark.parametrize("width", [1440, 390])
def test_each_day_with_a_forecast_says_its_weather_and_the_page_says_where_it_is_for_and_from_whom(agenda, width):
    """Owner, 2026-11-17: «Why isn't the weather for these days shown on the calendar?»"""
    page = agenda
    _open(page, width)
    note = page.locator(".agenda-read .agenda-weather").inner_text()
    assert "Weather for Wellington from Open-Meteo, read Today" in note
    if width > 640:
        marks = page.locator(".cal-heads .cal-head .cal-wx")
        assert marks.count() == 5, "the two days with no forecast show nothing"
        assert marks.first.inner_text() == "22° / 14°" and marks.first.locator("svg").count() == 1
        # The condition and the chance of rain are words on hover, never the picture alone.
        assert marks.nth(1).get_attribute("title") == "Showers, 70% chance of rain, 20° / 12°"
        assert marks.nth(2).get_attribute("title").startswith("Storm, 90% chance of rain")
        _column(page, 1).get_by_role("button", name="Dentist").click()
        assert "Clear, 5% chance of rain, 22° / 14°" in page.locator("dialog.cal-detail").inner_text()
        page.keyboard.press("Escape")
        page.get_by_role("button", name="Month", exact=True).click()
        assert page.locator('.cal-cell[data-day="2026-10-02"] .cal-wx').inner_text() == "20° / 12°"
        assert page.locator('.cal-cell[data-day="2026-10-08"] .cal-wx').count() == 0
    else:
        strip = page.locator(".cal-strip .cal-jump")
        assert strip.first.locator(".cal-wx").inner_text() == "22°" and strip.nth(6).locator(".cal-wx").count() == 0
        assert "Showers, 70% chance of rain, 20° / 12°" in page.locator("#cal-day-2026-10-02 .ag-dayhead").inner_text()
    # A failed read keeps the earlier forecast and says when it failed, why, and how old the forecast is.
    page.evaluate("""() => { REM.weather = { ...REM.weather, error: { at: '2026-10-01T06:10:00+00:00', reason: 'timed out', error: '' }, read_at: '2026-09-30T06:10:00+00:00' }; render(); }""", isolated_context=False)
    note = page.locator(".agenda-read .agenda-weather").inner_text()
    assert "Weather for Wellington could not be read on" in note and "(timed out)" in note and "The forecast is from" in note
    page.evaluate("() => { REM.weather = null; render(); }", isolated_context=False)
    assert page.locator(".cal-wx").count() == 0 and page.locator(".agenda-weather").count() == 0
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth")


def test_an_event_detail_shows_how_to_join_who_called_it_and_its_notes(agenda):
    """#3135 (owner, 2026-11-19): not only 'Open in Outlook'. A Meet link is said plainly, with the organiser and notes."""
    page = agenda
    _open(page, 1440)
    page.evaluate("""() => {
      const e = REM.calendar.events.find(e => e.title === 'Pilot renewal call with Fernhill');
      Object.assign(e, { meet: { url: 'https://meet.google.com/abc-defg-hij', service: 'Google Meet' }, organizer: 'Mara Ostrowski',
                         notes: 'Agenda:\\n1. Renewal terms' });
      render();
    }""", isolated_context=False)
    _column(page, 2).get_by_role("button", name="Pilot renewal call with Fernhill").click()
    detail = page.locator("dialog.cal-detail")
    join = detail.get_by_role("link", name="Join Google Meet")
    assert join.get_attribute("href") == "https://meet.google.com/abc-defg-hij"
    text = detail.inner_text()
    assert "Organised by Mara Ostrowski" in text and "1. Renewal terms" in text
    # The provider's page is the last, quiet thing: after the details, not instead of them.
    names = detail.locator("a").all_inner_texts()
    assert names[0] == "Join Google Meet" and names[-1].startswith("Open in Google Calendar")
    if os.environ.get("REM_PR_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["REM_PR_SHOTS"], "calendar-event-detail-1440.png"))


# ---------- #3152: the calendar is a component of Today ----------
TCAL_SHOTS = os.environ.get("REM_PR_SHOTS")


def _topmost(page, selector):
    return page.evaluate("""sel => { const n = document.querySelector(sel), b = n.getBoundingClientRect(), points = [];
      for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) points.push([b.left + 16 + (b.width - 32) * i / 4, b.top + 16 + (b.height - 32) * j / 4]);
      return points.filter(([x, y]) => y >= 0 && y < innerHeight && x < innerWidth).every(([x, y]) => n.contains(document.elementFromPoint(x, y))); }""",
                         selector, isolated_context=False)


@pytest.mark.parametrize("width", [1440, 390])
def test_today_shows_its_cards_then_the_calendar_and_no_day_plan_list(agenda, width):
    """Owner, 2026-11-19: «把我的日程放在 today 里面的一个 component，而不是单独的一个 category»; the cards come first."""
    page = agenda
    page.set_viewport_size({"width": width, "height": 900 if width > 640 else 844})
    page.evaluate("() => { location.hash = '#'; render(); }", isolated_context=False)
    cal = page.locator("#today-calendar")
    cal.wait_for()
    assert page.locator(".today-brief").bounding_box()["y"] < cal.bounding_box()["y"]
    assert page.locator(".day-plan-proposal").count() == 0 and "Your day" not in page.locator("#main").inner_text()
    # The seven days from today, with today's timeline under them; Thursday 1 Oct is today in the fixture.
    jumps = cal.locator(".tcal-strip .cal-jump")
    assert jumps.count() == 7 and jumps.first.get_attribute("aria-pressed") == "true" and "Today" in jumps.first.inner_text()
    assert cal.locator(".tcal-day .cal-day").count() == 1 and cal.locator(".tcal-day .cal-now").count() == 1
    assert cal.locator(".tcal-day .cal-ev", has_text="Quarterly receipts with Ines").count() == 1
    assert "#c=agenda" not in [a.get_attribute("href") for a in page.locator("#nav a").all()]
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    if TCAL_SHOTS:
        cal.scroll_into_view_if_needed()
        page.screenshot(path=os.path.join(TCAL_SHOTS, f"today-cal-after-{width}.png"))


def test_a_day_in_the_strip_switches_the_timeline_and_an_event_opens_on_top(agenda):
    page = agenda
    page.evaluate("() => { location.hash = '#'; render(); }", isolated_context=False)
    cal = page.locator("#today-calendar")
    cal.locator('.cal-jump[data-day="2026-10-02"]').click()
    assert cal.locator('.cal-jump[data-day="2026-10-02"]').get_attribute("aria-pressed") == "true"
    assert cal.locator('.tcal-day .cal-day[data-day="2026-10-02"]').count() == 1
    cal.locator(".tcal-day .cal-ev", has_text="Pilot renewal call with Fernhill").click()
    detail = page.locator("dialog.cal-detail")
    assert detail.locator("h2").inner_text() == "Pilot renewal call with Fernhill"
    assert _topmost(page, "dialog.cal-detail"), "the event's detail is covered"
    page.keyboard.press("Escape")


def test_the_week_and_the_month_open_in_place_and_fold_back(agenda):
    page = agenda
    page.evaluate("() => { location.hash = '#'; render(); }", isolated_context=False)
    cal = page.locator("#today-calendar")
    cal.get_by_role("button", name="Show the week").click()
    assert cal.locator(".agenda.agenda-week .cal-week").is_visible() and cal.locator(".cal-week .cal-day").count() == 7
    assert page.locator(".today-brief").count() == 1, "still Today"
    cal.get_by_role("button", name="Month").click()
    assert cal.locator(".agenda.agenda-month .cal-month").is_visible()
    assert _topmost(page, "#today-calendar .cal-month")
    if TCAL_SHOTS:
        page.screenshot(path=os.path.join(TCAL_SHOTS, "today-cal-after-month-1440.png"))
    cal.get_by_role("button", name="Back to the day").click()
    assert cal.locator(".tcal-strip").is_visible() and cal.locator(".agenda").count() == 0


@pytest.mark.parametrize("address", ["#c=agenda", "#view=agenda"])
def test_the_old_agenda_addresses_open_today_with_the_calendar_open(agenda, address):
    page = agenda
    page.evaluate(f"() => {{ location.hash = '{address}'; }}", isolated_context=False)
    page.locator("#today-calendar.expanded .cal-week").wait_for()
    assert page.locator(".today-brief").count() == 1
    assert page.locator("#nav a.active").get_attribute("href") == "#"


def test_the_day_plans_proposals_are_dashed_suggestions_that_lead_to_their_card(agenda):
    page = agenda
    page.evaluate("""() => {
      const card = REM.today_queue.find(row => !row.closed && !row.quiet);
      REM.day_plan = { days: [{ date: '2026-10-01', items: [
        { kind: 'proposal', key: card.key, keys: card.keys, record: card.record, title: 'x', text: 'Reply about the pilot', time: '15:00', end_time: '15:30' }] }] };
      window.suggested = card.record; location.hash = '#'; render();
    }""", isolated_context=False)
    block = page.locator("#today-calendar .cal-suggest")
    assert block.count() == 1 and block.inner_text().startswith("Suggested · ")
    assert block.evaluate("n => getComputedStyle(n).borderStyle") == "dashed"
    if TCAL_SHOTS:
        block.scroll_into_view_if_needed()
        page.screenshot(path=os.path.join(TCAL_SHOTS, "today-cal-after-suggested-1440.png"))
    block.click()
    page.wait_for_function("() => document.querySelector('#main .today-brief .qcard.raised, #main .today-brief .qcard.focal')?.dataset.path === window.suggested")
    page.locator("#today-calendar .tcal-drop").click()
    assert page.locator("#today-calendar .cal-suggest").count() == 0
    page.evaluate("() => render()", isolated_context=False)
    assert page.locator("#today-calendar .cal-suggest").count() == 0, "a dismissed suggestion stays gone"


def test_on_a_phone_the_strip_scrolls_sideways_and_the_page_does_not(agenda):
    page = agenda
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("() => { location.hash = '#'; render(); }", isolated_context=False)
    week = page.locator("#today-calendar .tcal-week")
    assert week.evaluate("n => n.scrollWidth > n.clientWidth")
    assert page.locator("#today-calendar .tcal-day .cal-week").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


# #3188 (hourly hunt on rc31): the detail sat at the far left over the rail and the event, the all-day lane held
# truncated red deadline chips, and the day timeline opened at 13:00 with the morning out of view.
@pytest.mark.parametrize("width", [1440])
def test_an_event_detail_opens_beside_its_event_without_covering_it(agenda, width):
    page = agenda
    page.set_viewport_size({"width": width, "height": 900})
    page.evaluate("() => { location.hash = ''; }", isolated_context=False)
    block = page.locator(".today-cal .cal-day .cal-event").first
    block.wait_for()
    block.scroll_into_view_if_needed()
    block.click()
    detail = page.locator("dialog.cal-detail")
    detail.wait_for()
    d, b = detail.bounding_box(), block.bounding_box()
    main = page.locator("#main").bounding_box()
    overlap = not (d["x"] >= b["x"] + b["width"] or d["x"] + d["width"] <= b["x"] or d["y"] >= b["y"] + b["height"] or d["y"] + d["height"] <= b["y"])
    assert not overlap, (d, b)
    assert d["x"] >= main["x"] - 1, "the detail never covers the rail"
    assert 0 <= d["x"] and d["x"] + d["width"] <= width and 0 <= d["y"]
    topmost = page.evaluate("""() => { const n = document.querySelector('dialog.cal-detail'), r = n.getBoundingClientRect(), pts = [];
      for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) pts.push([r.left + 16 + (r.width - 32) * i / 4, r.top + 16 + (r.height - 32) * j / 4]);
      return pts.filter(([x, y]) => y < innerHeight).every(([x, y]) => n.contains(document.elementFromPoint(x, y))); }""", isolated_context=False)
    assert topmost
    if os.environ.get("REM_PR_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["REM_PR_SHOTS"], f"cal-detail-{width}.png"))


def test_the_all_day_lane_holds_events_and_one_quiet_count_of_deadlines_per_day(agenda):
    page = agenda
    _open(page, 1440)
    lane = page.locator(".cal-allday")
    # No notebook date is drawn as a bar in the lane: no red truncated chips, no 'X owes the …' words.
    assert lane.locator(".cal-bar.cal-due, .cal-bar.cal-page, .cal-bar.late").count() == 0
    count = lane.locator(".cal-due-count").first
    assert count.is_visible()
    assert count.inner_text() == "1 due"
    page.evaluate("() => setInterfaceLanguage('zh')", isolated_context=False)
    assert page.locator(".cal-allday .cal-due-count").first.inner_text() == "1 个期限", "the lane's words are translated"
    page.evaluate("() => setInterfaceLanguage('en')", isolated_context=False)
    late = lane.locator(".cal-due-count.late")
    assert late.count() == 1 and "Fernhill invoice" in late.get_attribute("title")
    first = _column(page, 1).bounding_box()
    assert first["x"] <= late.bounding_box()["x"] <= first["x"] + first["width"]
    if os.environ.get("REM_PR_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["REM_PR_SHOTS"], "cal-week-lane-1440.png"))


def test_the_day_timeline_opens_with_the_days_first_event_in_view(agenda):
    page = agenda
    page.set_viewport_size({"width": 1440, "height": 900})
    page.evaluate("() => { location.hash = ''; }", isolated_context=False)
    # Late in the evening (the hunt saw 23:00): the old rule scrolled to now - 10 h, 13:00, past the morning.
    page.evaluate("() => { REM.as_of = REM.as_of.slice(0, 11) + '23:05:00+00:00'; overview(); }", isolated_context=False)
    scroll = page.locator(".today-cal .cal-scroll")
    scroll.wait_for()
    first = page.locator(".today-cal .cal-day .cal-event").first
    s, f = scroll.bounding_box(), first.bounding_box()
    assert s["y"] <= f["y"] < s["y"] + s["height"], "the first event of the day is in view on load"
    if os.environ.get("REM_PR_SHOTS"):
        page.locator(".today-cal").scroll_into_view_if_needed()
        page.screenshot(path=os.path.join(os.environ["REM_PR_SHOTS"], "cal-today-late-evening-1440.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator(".today-cal").scroll_into_view_if_needed()
        page.screenshot(path=os.path.join(os.environ["REM_PR_SHOTS"], "cal-today-390.png"))
        counts = page.locator(".today-cal .cal-due-count").evaluate_all("ns => ns.every(n => n.scrollWidth <= n.clientWidth)")
        assert counts, "a day's count is never cut on a phone"


@pytest.mark.parametrize("width", [1440, 390])
def test_the_first_screen_shows_the_next_event_beside_the_cards(agenda, width):
    """rc34 hunt: Today's calendar sat about 989px down. The cards stay first, but the first screen also says what is
    next: on a desk the side column lists the next events with a Join link and a 7-day strip; on a phone one line
    sits above the cards and takes you to the calendar."""
    page = agenda
    page.set_viewport_size({"width": width, "height": 900 if width > 640 else 844})
    page.evaluate("() => { overview(); }", isolated_context=False)
    selector = ".tnext" if width > 640 else ".tnext-line"
    nxt = page.locator(selector)
    nxt.wait_for()
    box = nxt.bounding_box()
    height = 900 if width > 640 else 844
    assert box and box["y"] + min(box["height"], 60) <= height, box  # its first line is on the first screen
    text = nxt.inner_text()
    assert any(title in text for title in ("Lunch with Mara", "Dentist", "Quarterly receipts", "Standup", "Pilot renewal")), text
    if width > 640:
        assert page.locator(".tnext .tnext-strip button").count() == 7
        # The cards are still the first thing in the work column.
        assert page.locator(".tgrid .deck").bounding_box()["x"] < box["x"]
    else:
        assert page.locator(".today-brief").bounding_box()["y"] > box["y"]  # above the cards on a phone
        nxt.click()
        page.wait_for_function("() => { const c = document.getElementById('today-calendar'); const b = c.getBoundingClientRect(); return b.top < innerHeight && b.bottom > 0; }")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.skipif(not os.environ.get("REM_PR_SHOTS"), reason="screenshots for a PR only")
@pytest.mark.parametrize("width", [1440, 390])
def test_pr_shots_today_first_screen(agenda, width):
    page = agenda
    page.set_viewport_size({"width": width, "height": 900 if width > 640 else 844})
    page.evaluate("() => { overview(); scrollTo(0, 0); }", isolated_context=False)
    page.screenshot(path=os.path.join(os.environ["REM_PR_SHOTS"], f"today-first-screen-{width}.png"))
    if width > 640 and page.locator(".tnext-ev").count():
        page.locator(".tnext-ev").first.click()
        page.wait_for_timeout(300)
        page.screenshot(path=os.path.join(os.environ["REM_PR_SHOTS"], f"today-next-detail-{width}.png"))
        # The opened detail is topmost (5x5 grid, 16px inset).
        assert page.evaluate("""() => { const d = document.querySelector('.cal-detail, .ag-detail, [class*=detail][role=dialog]'); if (!d) return true;
          const b = d.getBoundingClientRect(); let ok = true;
          for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) { const x = b.left + 16 + (b.width - 32) * i / 4, y = b.top + 16 + (b.height - 32) * j / 4;
            if (y < innerHeight && x < innerWidth && !d.contains(document.elementFromPoint(x, y))) ok = false; } return ok; }""", isolated_context=False)
