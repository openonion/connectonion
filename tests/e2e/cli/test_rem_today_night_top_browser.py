"""Today opens with the night (#3311, sprint T3): the sleep curve on top, the night's work under it on the same clock,
and every Today card with one primary step (#3312). Owner, 2026-11-22: «那个睡眠曲线……可以留着放在最上面……那个线
的下面，就是晚上做事情的时候». Invented notebook (tests/fixtures/rem_reader_notebook.py)."""
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")


@pytest.fixture(scope="module")
def page_file(tmp_path_factory):
    from connectonion.rem import reader as rem_reader
    from rem_reader_notebook import build
    root = tmp_path_factory.mktemp("t3") / "rem"
    build(root, datetime(2026, 11, 22, tzinfo=timezone.utc))
    path = root.parent / "reader.html"
    path.write_text(rem_reader.render(root, local=True), encoding="utf-8")
    return path


def _open(page_file, width, height, mobile=False, reduced=False):
    from patchright.sync_api import sync_playwright
    api = sync_playwright().start()
    browser = api.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": width, "height": height}, is_mobile=mobile, has_touch=mobile,
                              locale="en-US", reduced_motion="reduce" if reduced else "no-preference")
    page = ctx.new_page()
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(page_file.as_uri())
    page.locator("#main .night-card").wait_for()
    return api, browser, page


def test_the_curve_and_the_nights_work_open_today_above_the_first_card(page_file):
    api, browser, page = _open(page_file, 1440, 900)
    try:
        state = page.evaluate("""() => {
          const card = document.querySelector('#main .night-card'), hypno = card.querySelector('.hypno');
          const first = document.querySelector('#main .qcard');
          return {hypno: !!hypno, hypnoBottom: hypno && hypno.getBoundingClientRect().bottom,
                  firstTop: first && first.getBoundingClientRect().top, inFold: document.querySelectorAll('#processing .hypno').length};
        }""", isolated_context=False)
        assert state["hypno"], "the sleep curve is in Today's first card"
        assert state["inFold"] == 0, "the curve no longer hides in the bottom fold"
        assert state["firstTop"] is not None and state["hypnoBottom"] < state["firstTop"] < 900, state
    finally:
        browser.close(); api.stop()


def test_each_stretch_of_work_sits_in_the_night_log_popover_and_opens_to_its_pages(page_file):
    api, browser, page = _open(page_file, 1440, 900)
    try:
        log = page.locator("#main .night-card .nh-log")
        assert log.count() == 1 and not log.evaluate("el => el.open")
        log.locator("> summary").click()
        assert log.evaluate("el => el.open") is True
        rows = page.evaluate("""() => [...document.querySelectorAll('#main .night-card .nh-log .stretch')].map(s => ({
          text: s.innerText, from: Number(s.dataset.from), to: Number(s.dataset.to)
        }))""", isolated_context=False)
        assert len(rows) >= 2, rows
        for row in rows:
            assert 0 <= row["from"] <= row["to"] <= 100, row
            assert "–" in row["text"] or ":" in row["text"], "each stretch says when"
        stretch = page.locator("#main .night-card .nh-log .stretch").filter(has=page.locator(".stretch-pages")).first
        stretch.locator("summary").click()
        assert stretch.locator(".stretch-pages a").count() >= 1, "a stretch opens to the pages it changed"
        page.keyboard.press("Escape")
        assert stretch.evaluate("el => el.open") is False
    finally:
        browser.close(); api.stop()


def test_a_phone_lists_at_most_three_stretches_in_night_log_and_keeps_header_clean(page_file):
    """Art director on #3371 & #3470: up to three stretches inside Night log on a phone; 昨夜 header stays clean."""
    api, browser, page = _open(page_file, 390, 844, mobile=True)
    try:
        assert page.locator("#main .night-card .count-line, #main .night-card .deal").count() == 0
        assert page.locator("#main .night-card .nh").inner_text().strip() == "Last night"
        page.locator("#main .night-card .nh-log > summary").click()
        rows = page.evaluate("""() => [...document.querySelectorAll('#main .night-card .stretches.stacked .stretch > summary')].map(s =>
          ({h: s.getBoundingClientRect().height, text: s.innerText}))""", isolated_context=False)
        assert 1 <= len(rows) <= 3, rows
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth", isolated_context=False)
        head = page.locator("#main .deck > .desk-head.plain")
        assert head.count() == 1 and head.locator(".deal, .face").count() == 0
        assert head.bounding_box()["height"] < 32, "one line"
        assert head.bounding_box()["y"] + head.bounding_box()["height"] <= page.locator("#main .qcard").first.bounding_box()["y"] + 1
    finally:
        browser.close(); api.stop()


def test_the_chart_names_its_sleep_stages_and_draws_rem_sleep(page_file):
    """The owner's REM signature: 快速眼动 and 深睡 are named at the left, REM stretches drawn heavier."""
    for width, height, mobile in ((1440, 900, False), (390, 844, True)):
        api, browser, page = _open(page_file, width, height, mobile=mobile)
        try:
            levels = page.locator("#main .night-card .hypno .lvl").all_inner_texts()
            assert "REM sleep" in levels and "Deep sleep" in levels, (width, levels)
            assert page.locator("#main .night-card .hypno path.rem").count() == 1
            assert page.locator("#main .night-card .hypno path.area").count() == 1
            box = page.locator("#main .night-card .hypno .lvl").first.bounding_box()
            card = page.locator("#main .night-card").bounding_box()
            assert box["x"] >= card["x"], "the stage names sit inside the card"
        finally:
            browser.close(); api.stop()


def test_who_is_waiting_titles_the_desk_above_the_first_card(page_file):
    api, browser, page = _open(page_file, 1440, 900)
    try:
        assert page.locator("#main .night-card .count-line").count() == 0, "the night block speaks only of the night"
        head = page.locator("#main .deck > .desk-head .count-line").bounding_box()
        first = page.locator("#main .qcard").first.bounding_box()
        assert head["y"] + head["height"] <= first["y"] + 1
        line = page.locator("#main .desk-head .nb.solo").bounding_box()
        assert line["height"] < 60, "the count and its faces are one line"
    finally:
        browser.close(); api.stop()


def test_reduced_motion_draws_the_curve_without_animation(page_file):
    api, browser, page = _open(page_file, 1440, 900, reduced=True)
    try:
        name = page.evaluate("getComputedStyle(document.querySelector('#main .night-card .hypno .trace')).animationName")
        assert name in ("none", ""), name
    finally:
        browser.close(); api.stop()


def test_a_codex_debt_row_has_one_primary_the_three_closes_and_no_eight_links(page_file):
    """The handed row had eight links in one line (Mac rc11 pass); now: status, one step, the closes, 更多操作."""
    api, browser, page = _open(page_file, 1440, 900)
    try:
        page.evaluate("""() => { REM.as_of = '2026-11-22T09:00:00Z';
          const row = REM.today_queue.find(row => row.section === 'today');
          row.task = {id: 'a'.repeat(32), agent: 'codex', result: 'completed', record: 'people/ines-halvorsen.md'};
          REM.live = true; render(); }""", isolated_context=False)
        # People waiting come before an agent's not-overdue work, so the handed card is dealt behind them.
        order = page.evaluate("[...document.querySelectorAll('.today-brief .qcard')].map(c => !!c.querySelector('.handed'))", isolated_context=False)
        assert True in order and order[0] is False, order
        page.locator('.deal[data-path="people/ines-halvorsen.md"]').first.click()
        item = page.locator(".today-brief .qcard.focal .qitem").filter(has=page.locator(".handed")).first
        item.hover()
        line = item.locator(".handoff-line")
        outside = line.evaluate("""line => [...line.querySelectorAll('button, a')].filter(n => !n.closest('.row-more-menu'))
          .map(n => n.textContent.trim())""")
        assert line.locator(".strip-lead").count() == 1, outside
        for word in ("Mark done", "Not now", "Ignore"):
            assert word in outside, outside
        # One step, the three closes, and what is left: a single leftover is shown as itself, more go under 更多操作.
        assert len(outside) <= 5, outside
        if line.locator(".row-more").count():
            more = line.locator(".row-more > summary")
            assert more.inner_text().strip() == "More actions"  # a word, never a bare glyph (D-100)
            assert line.locator(".row-more-menu > *").count() >= 2, "a menu never holds a single item"
            more.click()
            assert line.locator(".row-more-menu > *").first.is_visible()
            page.keyboard.press("Escape")
            assert line.locator(".row-more").evaluate("el => el.open") is False
            assert page.evaluate("document.activeElement.classList.contains('row-more-btn')", isolated_context=False)
        else:
            assert "Show more" in outside, outside
    finally:
        browser.close(); api.stop()


BUSY_NIGHT = """() => {
  // Seven stretches across a night: reading only, rewriting pages, one stopped run; dense runs inside each.
  const end = new Date(REM.as_of).getTime(), runs = [];
  const plan = [[-9.5, 3, 0], [-8, 2, 1], [-6.6, 4, 0], [-5.2, 3, 1], [-3.9, 2, 0], [-2.4, 5, 1], [-0.9, 3, 1]];
  plan.forEach(([hours, n, changes], k) => { for (let i = 0; i < n; i++) {
    const at = end + hours * HOUR + i * 4 * 60e3;
    runs.push({run_id: 'busy-' + k + '-' + i, started_at: new Date(at).toISOString(), finished_at: new Date(at + 150e3).toISOString(),
      items: 6, changed: changes ? ['people/mara-ostrowski.md'] : [], outcome: k === 4 && i === 1 ? 'failed' : 'completed'});
  } });
  REM.logs = runs.reverse(); render();
}"""


def test_a_busy_night_rises_and_falls_through_the_stages(page_file):
    """Seven stretches: the chart climbs to REM where pages changed, to light sleep where it only read, and sinks to
    deep sleep between them, the rhythm reviewers asked to see (art director, #3371)."""
    import re
    api, browser, page = _open(page_file, 1440, 900)
    try:
        page.evaluate(BUSY_NIGHT, isolated_context=False)
        d = page.locator("#main .night-card .hypno .trace").get_attribute("d")
        ys = [float(y) for _, y in re.findall(r"([0-9.]+),([0-9.]+)(?=\s*(?:[MLCZ]|$))", d)]
        levels = sorted(set(ys))
        assert len(levels) >= 3, levels  # deep, light and REM at least
        sinks = sum(1 for a, b in zip(ys, ys[1:]) if b > a and b == max(ys))
        assert sinks >= 6, (sinks, d)  # back to deep sleep between stretches
        assert page.locator("#main .night-card .hypno path.rem").count() == 1
        assert page.locator("#main .night-card .stretch").count() + page.locator("#main .night-card .stretch-all").count() >= 3
    finally:
        browser.close(); api.stop()


STUCK_NIGHT = """() => {
  // Tonight on rc18 (#3379): one tag task retried every 15 minutes from 01:12, parked at 03:00, then translations and
  // a tag run that changed one page. The loop must read as awake, never as REM.
  const end = new Date(REM.as_of).getTime(), at = h => new Date(end + h * HOUR).toISOString(), runs = [];
  runs.push({run_id: 'stuck', phase: 'tag', started_at: at(-3.6), finished_at: at(-1.8), items: 0, changed: [], outcome: 'parked'});
  runs.push({run_id: 'after', phase: 'tag', started_at: at(-1.78), finished_at: at(-1.77), items: 0, changed: ['people/mara-ostrowski.md'], outcome: 'completed'});
  for (let i = 0; i < 6; i++) runs.push({run_id: 'tr' + i, phase: 'daily-translation', started_at: at(-1.75 + i * 0.1),
    finished_at: at(-1.7 + i * 0.1), items: 0, changed: [], outcome: 'completed'});
  REM.logs = runs.reverse(); render();
}"""


def test_a_stuck_loop_reads_as_awake_and_says_so(page_file):
    """A parked task's 108 minutes of retries are the night stuck awake: the trace stays at the Awake level over it,
    and the stretch under it says how long it was stuck and that it was skipped (#3379)."""
    api, browser, page = _open(page_file, 1440, 900)
    try:
        page.evaluate(STUCK_NIGHT, isolated_context=False)
        state = page.evaluate("""() => {
          const svg = document.querySelector('#main .night-card .hypno svg'), W = 1000;
          const d = svg.querySelector('.trace').getAttribute('d');
          const pts = [...d.matchAll(/([0-9.]+),([0-9.]+)(?=\\s*(?:[MLCZ]|$))/g)].map(m => [Number(m[1]), Number(m[2])]);
          const levels = [...document.querySelectorAll('#main .night-card .hypno .lvl')].map(s => parseFloat(s.style.top));
          const run = REM.logs.find(r => r.run_id === 'stuck'), s = hypnoScale(new Date(REM.as_of).getTime());
          const mid = s.x((runTime(run) + runEnd(run)) / 2);
          // The trace's level at the middle of the loop: the last point at or before it.
          const y = pts.filter(([x]) => x <= mid).pop()[1];
          const dot = document.querySelector('#main .night-card .hypno .dot.changed'), box = document.querySelector('#main .night-card .hypno').getBoundingClientRect();
          const dotX = dot ? W * (dot.getBoundingClientRect().left + dot.getBoundingClientRect().width / 2 - box.left) / box.width : null;
          return {y, levels, rem: svg.querySelector('path.rem')?.getAttribute('d') || '', mid, dotX, loopEnd: s.x(runEnd(run)),
                  words: [...document.querySelectorAll('#main .night-card .stretch-what')].map(n => n.textContent)};
        }""", isolated_context=False)
        assert state["y"] == state["levels"][0], state  # Awake, not REM sleep
        rem = state["rem"]
        for part in rem.split("M")[1:]:
            x0, x1 = float(part.split(",")[0]), float(part.split("L")[1].split(",")[0])
            assert not (x0 <= state["mid"] <= x1), state  # no REM stroke over the loop
        assert any("stuck" in w and "skipped automatically" in w for w in state["words"]), state["words"]
        assert state["dotX"] is not None and state["dotX"] >= state["loopEnd"] - 8, state  # the changed-page dot is not over the loop
    finally:
        browser.close(); api.stop()


def test_the_desk_title_says_which_cards_its_pager_pages_through(page_file):
    """«18 件在等你» over ‹ 1 / 2 ›: when the deck deals fewer cards than wait, the title names the set (#3379)."""
    for width, height, mobile in ((1440, 900, False), (390, 844, True)):
        api, browser, page = _open(page_file, width, height, mobile=mobile)
        try:
            # Live rc18: 18 waited, most held by an agent at work, and the deck dealt two cards. Hold the rest the same way.
            page.evaluate("""() => { const base = threadCounts; window.threadCounts = () => ({...base(), mine: base().mine + 14}); render(); }""",
                          isolated_context=False)
            state = page.evaluate("""() => ({mine: threadCounts().mine, cards: document.querySelectorAll('#main .deck .qcard').length,
              pager: document.querySelector('#main .qcount')?.textContent || '',
              scope: document.querySelector('#main .desk-head .count-scope')?.textContent || ''})""", isolated_context=False)
            n = state["pager"].split("/")[-1].strip() if state["pager"] else ""
            assert n and int(n) < state["mine"], state
            assert n in state["scope"], (width, state)
            head = page.locator("#main .deck > .desk-head").bounding_box()
            assert head["height"] < (32 if mobile else 60), "still one line"
        finally:
            browser.close(); api.stop()


def test_the_desk_title_adds_nothing_when_every_waiting_item_has_a_card(page_file):
    api, browser, page = _open(page_file, 1440, 900)
    try:
        assert page.locator("#main .desk-head .count-scope").count() == 0
    finally:
        browser.close(); api.stop()


def test_a_phone_names_awake_only_when_tonight_reaches_it(page_file):
    """On a phone an unnamed top level read as REM (art director on #3382): the phone names the levels the curve uses,
    so a stuck stretch brings 清醒's label, and a night that never woke has none."""
    api, browser, page = _open(page_file, 390, 844, mobile=True)
    try:
        page.evaluate(STUCK_NIGHT, isolated_context=False)
        levels = page.locator("#main .night-card .hypno .lvl").all_inner_texts()
        assert "Awake" in levels and "Deep sleep" in levels, levels
        page.evaluate("""() => { const end = new Date(REM.as_of).getTime(), at = h => new Date(end + h * HOUR).toISOString();
          REM.logs = [{run_id: 'calm', phase: 'investigate', started_at: at(-3), finished_at: at(-2.9), items: 4, changed: ['people/mara-ostrowski.md'], outcome: 'completed'}];
          render(); }""", isolated_context=False)
        levels = page.locator("#main .night-card .hypno .lvl").all_inner_texts()
        assert "Awake" not in levels and "REM sleep" in levels and "Deep sleep" in levels, levels
        page.evaluate(STUCK_NIGHT, isolated_context=False)
        boxes = [page.locator("#main .night-card .hypno .lvl").nth(i).bounding_box()
                 for i in range(page.locator("#main .night-card .hypno .lvl").count())]
        assert len(boxes) == 2, boxes  # two names fit; four on 8px levels overlapped
        for a, b in zip(boxes, boxes[1:]):
            assert a["y"] + a["height"] <= b["y"] + 0.5, boxes  # the labels never overlap
    finally:
        browser.close(); api.stop()
