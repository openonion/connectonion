"""Today says when, says each event once, and fits a phone (#3406, #3379).

The 08:25 hunt on rc20 found three things on the owner's Today:
(a) a card about a demo at 14:00 that day read 「2 天」, the thread's age, instead of 「今天 14:00」;
(b) 接下来 listed one Tuesday event twice, once from each of two calendars;
(c) the phone page scrolled sideways (406px at 390), pushed out by the stuck stretch's caption under the curve.
The notebook is invented (tests/fixtures/rem_reader_notebook.py) and read by the same render() path the Host uses."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


def _night(now: datetime) -> list[dict]:
    """A read, a tag task parked after 93 minutes of retries, then short runs: the night #3379's caption came from."""
    start = now - timedelta(hours=5.5)
    iso = lambda t: t.isoformat(timespec="seconds")
    runs = [{"phase": "sync", "started_at": iso(start), "finished_at": iso(start + timedelta(minutes=3)),
             "outcome": "completed", "items": 12, "changed": []},
            {"phase": "tag", "started_at": iso(start + timedelta(minutes=12)),
             "finished_at": iso(start + timedelta(minutes=105)), "outcome": "parked", "items": 0, "changed": []}]
    # The loop's own failed turns: on the owner's night they made the stuck caption long enough to widen the page.
    runs += [{"phase": "tag", "started_at": iso(start + timedelta(minutes=15 + 15 * i)),
              "finished_at": iso(start + timedelta(minutes=16 + 15 * i)), "outcome": "failed", "items": 0, "changed": []}
             for i in range(6)]
    for i in range(40):
        at = start + timedelta(minutes=110 + i * 5)
        runs.append({"phase": "daily-translation" if i % 3 else "investigate", "started_at": iso(at),
                     "finished_at": iso(at + timedelta(minutes=2)), "outcome": "completed", "items": 3,
                     "changed": ["people/mara-ostrowski.md"] if i % 3 == 0 else []})
    return runs


@pytest.fixture(scope="module")
def page_file(tmp_path_factory):
    from connectonion.rem import reader as rem_reader
    from rem_reader_notebook import build
    root = tmp_path_factory.mktemp("urgency") / "rem"
    now = datetime.now(timezone.utc)
    build(root, now - timedelta(days=2))
    runs = root / ".state" / "runs"
    for i, run in enumerate(_night(now)):
        run["id"] = f"run_{0xdef000 + i:032x}"
        (runs / f"{run['id']}.json").write_text(json.dumps(run))
    path = root.parent / "reader.html"
    path.write_text(rem_reader.render(root, local=True), encoding="utf-8")
    return path


def _open(page_file, width, height, mobile=False, locale="en-US"):
    from patchright.sync_api import sync_playwright
    api = sync_playwright().start()
    browser = api.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=mobile, has_touch=mobile, locale=locale)
    page = ctx.new_page()
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(page_file.as_uri())
    page.locator("#main .today-brief").wait_for()
    return api, browser, page


# A thread two days old about something 90 minutes from now: said by when first, from the person's calendar event or
# from the thread's own words (the owner's card read 「Alyssa 提议11月23日周一14:00演示」 and showed 「2 天」).
SOON = """() => {
  const r = inCategory('people')[0], now = Date.parse(REM.as_of), since = agDay(agToday(), -2);
  const start = new Date(now + 90 * 60e3).toISOString(), end = new Date(now + 150 * 60e3).toISOString();
  const word = day => day === agToday() ? agT('Today') : agT('Tomorrow');
  REM.calendar = { events: [{ id: 'demo-1', start, end, title: 'Product demo', calendar: 'google', people: [r.path] }] };
  const byEvent = threadAge({ since, text: 'Asked to see the product.' }, r);
  // Another person's event the same day is not this thread's time (art director on #3408).
  const other = inCategory('people').find(p => p.path !== r.path);
  REM.calendar = { events: [{ id: 'demo-2', start, end, title: 'Someone else demo', calendar: 'google', people: [other.path] }] };
  const notMine = threadAge({ since, text: 'Asked to see the product.' }, r);
  REM.calendar = { events: [{ id: 'demo-3', start, end, title: 'No attendees', calendar: 'google', people: [] }] };
  const noAttendee = threadAge({ since, text: 'Asked to see the product.' }, r);
  REM.calendar = { events: [] };
  const [y, m, d] = agToday().split('-').map(Number);
  const zh = threadAge({ since, text: `提议${m}月${d}日周一14:00演示，草稿说明演示时长。` }, r);
  const en = threadAge({ since, text: `Proposed a demo on ${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m - 1]} ${d} at 2pm.` }, r);
  const old = threadAge({ since, text: 'We met last spring, demo went well.' }, r);
  return { byEvent, notMine, noAttendee, eventWant: word(calendarDay(start)) + ' ' + agTime(start), zh, en, old, today: agT('Today'),
           ageWord: age(since), waiting: t('waiting {age}', { age: age(since) }) };
}"""


def test_a_thread_about_something_today_says_when_first(page_file):
    api, browser, page = _open(page_file, 1440, 1000)
    try:
        got = page.evaluate(SOON, isolated_context=False)
        assert got["byEvent"] == got["eventWant"] + " · " + got["waiting"], got  # the age has its word beside a time
        assert got["notMine"] == got["ageWord"], got
        assert got["noAttendee"] == got["ageWord"], got
        assert got["zh"].startswith(got["today"] + " 14:00"), got
        assert got["en"].startswith(got["today"] + " 14:00"), got
        assert got["old"] == got["ageWord"], got  # no date in the words, no event: the age alone, as before
    finally:
        browser.close(); api.stop()


TWINS = """() => {
  const now = Date.parse(REM.as_of), start = new Date(now + 26 * 3600e3).toISOString(), end = new Date(now + 27 * 3600e3).toISOString();
  REM.calendar = { events: [
    { id: 'g-1', start, end, title: 'Weekly sync', calendar: 'google', people: [] },
    { id: 'm-9', start, end, title: 'Weekly  sync ', calendar: 'microsoft', people: [], meet: { url: 'https://example.invalid/j', service: 'Teams' } } ] };
  render();
  const shown = [...document.querySelectorAll('#main .tnext .tnext-title')].filter(n => /weekly\\s+sync/i.test(n.textContent)).length;
  const kept = agendaEntries().filter(e => e.kind === 'event' && /weekly\\s+sync/i.test(e.title));
  return { shown, kept: kept.length, meet: kept[0] && kept[0].meet && kept[0].meet.service };
}"""


def test_one_event_in_two_calendars_shows_once(page_file):
    api, browser, page = _open(page_file, 1440, 1000)
    try:
        got = page.evaluate(TWINS, isolated_context=False)
        assert got["kept"] == 1, got
        assert got["shown"] == 1, got
        assert got["meet"] == "Teams", got  # the copy that had the join link lends it to the one kept
    finally:
        browser.close(); api.stop()


# Any caption, however long, wraps inside the card. The owner's 「读了 651 项 · 改写了 38 页 · 21 次运行提前停止」 made the
# page 406px wide: a stacked stretch kept its one-line width (nowrap, and a grid item's automatic min-width).
LENGTHEN = """(zh) => { const words = zh ? ['读了 651 项', '改写了 38 页', '21 次运行提前停止'] : ['read 651 items', 'rewrote 38 pages', '21 runs stopped early'];
  for (const n of document.querySelectorAll('#main .night-card .stretch-what'))
    n.replaceChildren(...words.flatMap((w, i) => [el('span', { class: 'clause', text: w + (i < words.length - 1 ? ' ·' : '') }), i < words.length - 1 ? ' ' : ''])
      .map(c => typeof c === 'string' ? document.createTextNode(c) : c)); }"""
WIDTH = """() => ({ page: document.documentElement.scrollWidth, view: window.innerWidth,
  broken: [...document.querySelectorAll('#main .night-card .stretch-what .clause')].filter(c => c.getClientRects().length > 1).map(c => c.textContent),
  captions: [...document.querySelectorAll('#main .night-card .stretch')].map(n => {
    const b = n.getBoundingClientRect(); return { right: Math.round(b.right), text: n.textContent };
  }) })"""


@pytest.mark.parametrize("locale", ["en-US", "zh-CN"])
def test_phone_today_never_scrolls_sideways(page_file, locale):
    api, browser, page = _open(page_file, 390, 844, mobile=True, locale=locale)
    try:
        if locale == "zh-CN":
            page.evaluate("() => setInterfaceLanguage('zh')", isolated_context=False)
            page.locator("#main .today-brief").wait_for()
        page.wait_for_timeout(300)
        page.evaluate(LENGTHEN, locale == "zh-CN", isolated_context=False)
        got = page.evaluate(WIDTH, isolated_context=False)
        # Against the phone's own 390, not innerWidth: a mobile layout viewport grows to fit what overflows it.
        assert got["page"] <= 390, got
        assert all(c["right"] <= 390 for c in got["captions"]), got
        assert any("21" in c["text"] for c in got["captions"]), got  # wrapped, not cut: the end of the line is still there
        assert not got["broken"], got  # lines break between clauses, never inside one (no lone 「止」)
    finally:
        browser.close(); api.stop()
