"""Projects shows activity over time, in one design across its three views and the record (#3096).

The owner, 2026-11-17, on his real notebook: «The timeline and the list use different type. GitHub's
contribution record shows activity clearly; here I cannot see it, and I cannot scroll back and forward
without end. Why is the most frequent activity not at the top, as in People? Why is the type so small?»

Counting and order are held in tests/unit/test_rem_project_activity.py; these read what is drawn. Every
name, sentence and count here is invented.
"""

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_rem_reader_design_browser import PROJECT_SET, reader  # noqa: E402,F401

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)

# What project_activity.attach would hand the page, written out: this week is the one of 28 September 2026.
ACTIVITY_SET = r"""() => {
  const weeks = {
    'atlas': {'2026-07-13': 2, '2026-08-31': 4, '2026-09-07': 9, '2026-09-14': 3, '2026-09-21': 12, '2026-09-28': 1},
    'fernhill-pilot': {'2026-09-14': 1, '2026-09-21': 5, '2026-09-28': 6},
    'capstone-review': {'2026-09-07': 2, '2026-09-21': 3},
    'tidewater': {'2026-08-31': 1},
    'workshop': {'2026-06-29': 7, '2026-07-13': 2}};
  const order = ['fernhill-pilot', 'atlas', 'capstone-review', 'tidewater', 'workshop'];
  REM.project_activity = {scale: [1, 3, 6, 10], kinds: {messages: 51, sessions: 5, mail: 1, page: 1}, first: '2026-06-29',
    this_week: '2026-09-28', quiet_days: 30, recent_weeks: 12};
  for (const r of REM.records.filter(r => r.category === 'projects')) {
    const slug = r.path.slice(9, -3), mine = weeks[slug] || {}, days = Object.keys(mine).sort();
    const rank = order.includes(slug) ? order.indexOf(slug) : 50;
    r.activity = {weeks: mine, kinds: {}, first: days[0] || '', last: days.at(-1) || '', recent: 0, rank,
      quiet: !days.length || days.at(-1) < '2026-08-31'};
  }
  REM.today_queue = [...(REM.today_queue || []), {record: 'projects/atlas.md', key: 'a', keys: ['a'], section: 'waiting'},
    {record: 'projects/atlas.md', key: 'b', keys: ['b'], section: 'waiting'}];
  render();
}"""
RAW = ["outcome unknown", "Owner unconfirmed", "Agent request", "You owe Mara the weekly chart report", "Mark done"]


def _open(reader, hash_, width=1440):
    page, uri = reader
    page.set_viewport_size({"width": width, "height": 900 if width == 1440 else 844})
    page.goto(uri + hash_)
    page.evaluate(PROJECT_SET, isolated_context=False)
    page.evaluate(ACTIVITY_SET, isolated_context=False)
    return page


def _paths(page, selector):
    return page.evaluate(f"[...document.querySelectorAll('{selector}')].map(n => n.dataset.path.slice(9, -3))", isolated_context=False)


def _smallest_text(page, selector):
    """The smallest computed size of any element under `selector` that shows text of its own."""
    return page.evaluate("""(selector) => Math.min(...[...document.querySelectorAll(selector + ' *')]
      .filter(n => [...n.childNodes].some(c => c.nodeType === 3 && c.textContent.trim()) && n.getClientRects().length)
      .map(n => parseFloat(getComputedStyle(n).fontSize)))""", selector, isolated_context=False)


@pytest.mark.parametrize("width", [1440, 390])
def test_the_timeline_is_a_square_a_week_under_named_months_on_one_scale(reader, width):
    from patchright.sync_api import expect

    page = _open(reader, "#c=projects&v=timeline", width)
    expect(page.locator(".pa-time .pa-months")).to_have_count(1)  # one axis for every row
    months = page.locator(".pa-month").all_inner_texts()
    assert {"Aug", "Sep", "Oct"} <= set(months) and "Jan 2026" in months, months
    expect(page.locator(".pa-month.now")).to_have_text("Sep")
    # Every row is the same weeks, so a column is the same week all the way down.
    counts = page.evaluate("[...new Set([...document.querySelectorAll('.pa-canvas .pa-strip')].map(s => s.children.length))]",
                           isolated_context=False)
    assert len(counts) == 1 and counts[0] >= 52
    atlas = page.locator('.pa-canvas .pa-strip[data-path="projects/atlas.md"]')
    busy = atlas.locator('.pa-c[data-w="2026-09-21"]')
    expect(busy).to_have_class(re.compile(r"\bl4\b"))
    expect(busy).to_have_attribute("aria-label", "12 activities in the week of Sep 21, 2026")
    expect(atlas.locator('.pa-c[data-w="2026-09-28"]')).to_have_class(re.compile(r"\bl1\b.*\bnow\b"))
    expect(atlas.locator('.pa-c[data-w="2026-09-28"]')).to_have_attribute("aria-label", "1 activity in the week of Sep 28, 2026")
    expect(atlas.locator('.pa-c[data-w="2026-08-24"]')).to_have_attribute("aria-label", "No activity in the week of Aug 24, 2026")
    expect(atlas.locator('.pa-c[data-w="2026-10-05"]')).to_have_class(re.compile(r"\bahead\b"))
    # The same count is the same step in another row.
    fern = page.locator('.pa-canvas .pa-strip[data-path="projects/fernhill-pilot.md"]')
    expect(fern.locator('.pa-c[data-w="2026-09-28"]')).to_have_class(re.compile(r"\bl3\b"))
    # The words are shown where he points, and on a tap.
    if width == 1440:
        busy.hover()
    else:
        busy.focus()
    expect(page.locator("#pa-tip")).to_have_text("12 activities in the week of Sep 21, 2026")
    # Each row says, from its own weeks, when it was busiest and how long it has been still.
    name = lambda slug: page.locator(f'.pa-name[data-path="projects/{slug}.md"]')
    expect(name("atlas").locator(".pa-say")).to_have_text("Busiest in September; active this week")
    expect(name("capstone-review").locator(".pa-say")).to_have_text("Busiest in September; active last week")
    expect(name("tidewater").locator(".pa-say")).to_have_text("Busiest in August; quiet for 4 weeks")
    expect(name("grant").locator(".pa-say")).to_have_text("No dated activity on record")
    # The legend says in words what a square counts and what a shade means.
    expect(page.locator(".pa-counted")).to_contain_text("One square is one week")
    expect(page.locator(".pa-counted")).to_contain_text("51 messages you typed to agents")
    assert page.locator(".pa-scale .pa-c").count() == 5
    expect(page.locator(".pa-scale .pa-c").nth(4)).to_have_attribute("aria-label", "10 or more in a week")
    assert _smallest_text(page, ".pd") >= 13
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_the_order_is_peoples_rule_said_on_the_page_with_the_quiet_below_a_worded_divider(reader):
    from patchright.sync_api import expect

    page = _open(reader, "#c=projects&v=timeline")
    expect(page.locator(".pa-order")).to_have_text(
        "Most recently active first, the same order as People; within a week, the busier project first.")
    names = _paths(page, ".pa-name")
    assert names[:4] == ["fernhill-pilot", "atlas", "capstone-review", "tidewater"]
    assert names == _paths(page, ".pa-canvas .pa-strip")  # a name and its strip are the same row
    divider = page.locator(".pa-names .pa-divider")
    quiet = len(names) - 4
    expect(divider).to_have_text(f"Quiet for more than 30 days · {quiet}")
    below = page.evaluate("""() => { const line = document.querySelector('.pa-names .pa-divider').getBoundingClientRect().top;
      return [...document.querySelectorAll('.pa-name')].filter(n => n.getBoundingClientRect().top > line).map(n => n.dataset.path.slice(9, -3)); }""",
                          isolated_context=False)
    assert "workshop" in below and "atlas" not in below and len(below) == quiet
    # A name sits level with its strip.
    level = page.evaluate("""() => [...document.querySelectorAll('.pa-name')].every(n => {
      const strip = document.querySelector('.pa-canvas .pa-strip[data-path="' + n.dataset.path + '"]').getBoundingClientRect();
      return Math.abs(strip.top - n.getBoundingClientRect().top) < 1; })""", isolated_context=False)
    assert level
    page.evaluate("setInterfaceLanguage('zh')", isolated_context=False)
    expect(page.locator(".pa-order")).to_contain_text("「人物」")
    expect(page.locator('.pa-name[data-path="projects/atlas.md"] .pa-say')).to_have_text("9月最忙；本周有活动")


def test_time_scrolls_back_and_forward_without_an_end_and_today_returns(reader):
    from patchright.sync_api import expect

    page = _open(reader, "#c=projects&v=timeline")
    time, first = page.locator(".pa-time"), page.locator(".pa-canvas .pa-strip").first
    in_view = "(n) => { const a = n.getBoundingClientRect(), b = n.closest('.pa-time').getBoundingClientRect(); return a.left >= b.left && a.right <= b.right; }"
    now = first.locator(".pa-c.now")
    assert now.evaluate(in_view)  # it opens on this week
    assert time.evaluate("n => n.scrollLeft") > 0
    before, earliest = first.locator(".pa-c").count(), first.locator(".pa-c").first.get_attribute("data-w")
    for _ in range(3):  # back, and back again: there is no first week
        held = first.locator(".pa-c").count()
        time.evaluate("n => { n.scrollLeft = 0; }")
        expect(first.locator(".pa-c")).to_have_count(held + 26)
        assert time.evaluate("n => n.scrollLeft") > 0  # the view is held where it was, with more behind it
    assert first.locator(".pa-c").first.get_attribute("data-w") < earliest
    assert first.locator(".pa-c").count() == before + 78
    assert "Jan 2025" in page.locator(".pa-month").all_inner_texts()
    # Workshop's weeks from June were not in the first window's view; they are drawn from the data he already has.
    expect(page.locator('.pa-canvas .pa-strip[data-path="projects/workshop.md"] .pa-c[data-w="2026-06-29"]')).to_have_class(re.compile(r"\bl3\b"))
    assert not now.evaluate(in_view)
    held = first.locator(".pa-c").count()
    time.evaluate("n => { n.scrollLeft = n.scrollWidth; }")  # forward: the weeks to come are simply empty
    expect(first.locator(".pa-c")).to_have_count(held + 26)
    page.get_by_role("button", name="Today").click()
    assert now.evaluate(in_view)
    # ← and → land on the first week of a month.
    time.focus()
    edge = "n => { const step = n.querySelector('.pa-strip').children[1].offsetLeft - n.querySelector('.pa-strip').children[0].offsetLeft; const i = Math.round(n.scrollLeft / step); const c = n.querySelector('.pa-strip').children; return [c[i].dataset.w.slice(0, 7), c[i - 1].dataset.w.slice(0, 7)]; }"
    seen = []
    for key in ("ArrowLeft", "ArrowLeft", "ArrowRight"):
        page.keyboard.press(key)
        month, previous = time.evaluate(edge)
        assert month != previous
        seen.append(month)
    assert seen[1] < seen[0] and seen[2] == seen[0]
    page.keyboard.press("Home")
    assert now.evaluate(in_view)


@pytest.mark.parametrize("width", [1440, 390])
def test_the_list_is_the_same_rows_as_a_table_at_body_size(reader, width):
    from patchright.sync_api import expect

    page = _open(reader, "#c=projects&v=list", width)
    if width == 1440:
        expect(page.locator(".pl-head > div")).to_have_text(["Project", "Status", "Last active", "Last 12 weeks", "Open"])
    assert _paths(page, ".pl-row[data-path]")[:4] == ["fernhill-pilot", "atlas", "capstone-review", "tidewater"]
    expect(page.locator(".pl .pa-divider")).to_contain_text("Quiet for more than 30 days")
    atlas = page.locator('.pl-row[data-path="projects/atlas.md"]')
    expect(atlas.locator(".pa-title")).to_have_text("Atlas")
    expect(atlas.locator(".pa-say")).to_have_text("The shared mapping toolkit.")
    expect(atlas.locator(".pl-state")).to_have_text("Active")
    expect(atlas.locator(".pl-last")).to_contain_text("Sep 28")
    expect(atlas.locator(".pl-strip .pa-c")).to_have_count(12)
    expect(atlas.locator('.pl-strip .pa-c[data-w="2026-09-21"]')).to_have_class(re.compile(r"\bl4\b"))
    expect(atlas.locator(".pl-open a")).to_have_text("2 in Today")
    expect(page.locator('.pl-row[data-path="projects/capstone-review.md"] .pl-state .red')).to_have_text("14 days late")
    # Table text is body size, the same as the timeline's rows: the name, the sentence and every cell.
    sizes = page.evaluate("""() => [...document.querySelectorAll('.pl-row[data-path] .pa-title, .pl-row[data-path] .pa-say, .pl-row[data-path] [role=cell]')]
      .map(n => getComputedStyle(n).fontSize)""", isolated_context=False)
    assert set(sizes) == {"15px"}
    assert _smallest_text(page, ".pd") >= 13
    main = page.locator("#main").inner_text()
    assert not [words for words in RAW if words in main]
    assert "REM read" not in main and "On file" not in main
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.evaluate("setInterfaceLanguage('zh')", isolated_context=False)
    if width == 1440:
        expect(page.locator(".pl-head > div")).to_have_text(["项目", "状态", "最近活动", "最近 12 周", "未完成"])


def test_one_row_rhythm_and_one_type_across_the_timeline_and_the_list(reader):
    page = _open(reader, "#c=projects&v=timeline")
    look = """(selector) => { const row = document.querySelector(selector), name = getComputedStyle(row.querySelector('.pa-title')),
      say = getComputedStyle(row.querySelector('.pa-say'));
      return [Math.round(row.getBoundingClientRect().height), name.fontFamily, name.fontSize, name.fontWeight, say.fontSize, say.color]; }"""
    timeline = page.evaluate(look, '.pa-name[data-path="projects/atlas.md"]', isolated_context=False)
    page.goto(page.url.split("#")[0] + "#c=projects&v=list")
    page.evaluate(PROJECT_SET, isolated_context=False)
    page.evaluate(ACTIVITY_SET, isolated_context=False)
    assert page.evaluate(look, '.pl-row[data-path="projects/atlas.md"]', isolated_context=False) == timeline


@pytest.mark.parametrize("width", [1440, 390])
def test_a_board_card_is_a_name_a_sentence_its_weeks_and_its_last_date(reader, width):
    from patchright.sync_api import expect

    page = _open(reader, "#c=projects&v=board", width)
    card = page.locator('.pd-card[data-path="projects/fernhill-pilot.md"]')
    expect(card.locator(".pa-title")).to_have_text("Fernhill pilot")
    expect(card.locator(".pa-say")).to_have_text("A paid pilot of the weekly brief for Fernhill Labs.")
    expect(card.locator(".pa-mini .pa-c")).to_have_count(12)
    expect(card.locator(".pd-when")).to_have_text("Sep 28")
    assert page.locator(".pd-step, .pd-step-who, .pd-owner").count() == 0
    late = page.locator('.pd-card[data-path="projects/capstone-review.md"]')
    expect(late.locator(".pd-card-when .red")).to_have_text("14 days late")
    main = page.locator("#main").inner_text()
    assert not [words for words in RAW if words in main]
    # A card's order in its column is the page's one order.
    active = _paths(page, '.pd-state-col[data-state="active"] .pd-card')
    assert active.index("fernhill-pilot") < active.index("atlas")
    assert _smallest_text(page, ".pd") >= 13
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_a_project_record_is_knowledge_and_sends_open_work_to_today(reader, width):
    from patchright.sync_api import expect

    page = _open(reader, "#r=projects%2Fatlas.md", width)
    focus = page.locator(".record-focus.projects")
    expect(focus.locator(".project-what")).to_have_text("The shared mapping toolkit.")
    expect(focus.locator(".project-activity h2")).to_have_text("Activity")
    expect(focus.locator(".project-activity p")).to_have_text("Busiest in September; active this week.")
    expect(focus.locator(".project-weeks .pa-c")).to_have_count(26)
    assert {"Jul", "Aug", "Sep"} <= set(focus.locator(".project-weeks .pa-month").all_inner_texts())
    expect(focus.locator('.project-weeks .pa-c[data-w="2026-09-21"]')).to_have_attribute("aria-label", "12 activities in the week of Sep 21, 2026")
    assert focus.locator('.project-weeks .pa-c.now').evaluate(
        "n => n.getBoundingClientRect().right <= n.closest('.project-weeks').getBoundingClientRect().right + 1")
    # Nothing on the record is a task: no step rows, no buttons, one line that counts and leads to Today.
    assert focus.locator(".project-step, .thread-actions, button").count() == 0
    assert "Mark done" not in page.locator("#main").inner_text()
    page.locator("details.deep-note > summary").click()
    assert "Mark done" not in page.locator("#main").inner_text()
    assert page.locator("#main .thread-actions").count() == 0
    line = focus.locator(".project-today a")
    expect(line).to_have_text("2 open items are in Today")
    assert _smallest_text(page, ".record-focus.projects") >= 13
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    line.click()
    expect(page.locator(".today-brief, .today, #main .n3-today").first).to_be_visible()


def test_a_project_record_carries_no_translation_note_of_its_own(reader):
    """#3096 put the note at the record's end; #3143 moves it to the top bar's one language control."""
    page = _open(reader, "#r=projects%2Fatlas.md")
    page.evaluate("""() => { REM.status.worker = {...(REM.status.worker || {}), enabled: true};
      REM.status.translation_coverage = {zh: {requested: true}}; setInterfaceLanguage('zh'); }""", isolated_context=False)
    assert page.locator("#main .translation-line, #main .translate-all").count() == 0


@pytest.mark.parametrize("view", ["timeline", "list", "board"])
def test_on_a_phone_nothing_is_left_under_the_tab_bar(reader, view):
    page = _open(reader, "#c=projects&v=" + view, 390)
    page.evaluate("scrollTo(0, document.documentElement.scrollHeight)")
    clear = page.evaluate("""() => { const bar = document.querySelector('.tabbar').getBoundingClientRect();
      const rows = [...document.querySelectorAll('.pa-name, .pa-canvas .pa-strip, .pl-row, .pd-card')];
      return Math.max(...rows.map(n => n.getBoundingClientRect().bottom)) <= bar.top; }""", isolated_context=False)
    assert clear
    if view == "timeline":
        # The squares are smaller and fewer fit, but a count is the same step as on a desk.
        cell = page.locator('.pa-canvas .pa-strip[data-path="projects/atlas.md"] .pa-c[data-w="2026-09-21"]')
        assert cell.evaluate("n => [n.offsetWidth, n.className.includes('l4')]") == [14, True]
        fit = page.evaluate("""() => { const time = document.querySelector('.pa-time'), cells = time.querySelector('.pa-strip').children;
          return Math.floor(time.clientWidth / (cells[1].offsetLeft - cells[0].offsetLeft)); }""", isolated_context=False)
        assert 16 <= fit <= 24
        # A name and its sentence sit above their squares, not on them.
        apart = page.evaluate("""() => [...document.querySelectorAll('.pa-name')].every(n => {
          const say = n.querySelector('.pa-say').getBoundingClientRect();
          const cell = document.querySelector('.pa-canvas .pa-strip[data-path="' + n.dataset.path + '"] .pa-c').getBoundingClientRect();
          return say.bottom <= cell.top; })""", isolated_context=False)
        assert apart

