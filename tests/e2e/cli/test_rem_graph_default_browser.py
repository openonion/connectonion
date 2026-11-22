"""The graph is the first thing a newcomer sees in Knowledge, so it has to say what it shows (#3085; opt in).

A designer refused the graph as a default on a real notebook of about 200 marks: no key for the five shapes
(it was drawn under the fold), five labels of which four were cut mid-phrase and one sat on a mark, a panel that
repeated the cut titles and was two-thirds empty, marks nobody could tap on a phone, a title that changed size
between Graph and Entries, and a green button. The owner's rules: say it in words, never by shape alone; fewer
words; one hierarchy per screen. The notebook is the invented one in tests/fixtures/rem_graph_notebook.py.
"""

import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

HEAT = "Heat storage for off-grid dairy barns in cold valleys"
BUSIEST = "Barn retrofit for the upper valley dairies"



# The 3D map is the desktop default (#3309) and has its own tests (test_rem_live_graph_browser.py). These pages
# pin the 2D map, which a phone, reduced motion and the owner's 2D choice still draw, so its labels, marks
# and canvas keep their coverage.
PIN_2D = "try { localStorage.setItem('co-rem-graph-dim', '2d'); } catch (e) {}"

@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from rem_graph_notebook import build
    from connectonion.rem.reader import render
    tmp = tmp_path_factory.mktemp("graph")
    path = tmp / "reader.html"
    path.write_text(render(build(tmp / "rem"), local=True), encoding="utf-8")
    return path.as_uri()


@pytest.fixture(scope="module")
def browser():
    from patchright.sync_api import sync_playwright
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        yield browser
        browser.close()


def open_graph(browser, uri, width=1440, hash_="#c=knowledge", language="en"):
    page = browser.new_page(viewport={"width": width, "height": 900 if width > 400 else 844}, locale="en-US", has_touch=width < 400)
    page.add_init_script(PIN_2D)
    page.errors = []
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(uri)
    page.locator("#nav a").first.wait_for(state="attached")
    if language != "en":
        page.evaluate("language => setInterfaceLanguage(language)", language, isolated_context=False)
    page.evaluate("hash => { location.hash = hash; }", hash_)
    page.locator(".gx-map canvas, .gx-topics").first.wait_for()
    page.wait_for_timeout(150)
    return page


def js(page, script, arg=None):
    return page.evaluate(script, arg, isolated_context=False)


def test_one_sentence_says_what_the_map_shows_and_it_is_the_key_to_the_shapes(browser, built):
    page = open_graph(browser, built)
    says = page.locator(".gx-says")
    assert " ".join(says.inner_text().split()) == (
        "5 tag pages link 110 people, 32 projects and 24 organisations, with 6 skills and decisions. "
        f"The busiest is {BUSIEST}, with 19 links.")
    # Each shape stands beside its word and its count, so no mark on the map is a shape alone.
    keys = page.locator(".gx-says .gx-key")
    assert keys.all_inner_texts() == ["5 tag pages", "110 people", "32 projects", "24 organisations", "6 skills and decisions"]
    assert keys.evaluate_all("keys => keys.every(key => key.querySelector('svg.gx-glyph'))")
    # It was drawn under the fold: the map was as tall as the window but started under the top bar.
    assert js(page, "() => document.documentElement.scrollHeight <= innerHeight"), "the map fits the window; nothing to scroll to"
    for part in (".gx-says", ".gx-legend", ".gx-canvas"):
        box = page.locator(part).bounding_box()
        assert box["y"] >= 0 and box["y"] + box["height"] <= 900, (part, box)
    assert says.bounding_box()["y"] + says.bounding_box()["height"] <= page.locator(".gx-canvas").bounding_box()["y"]
    assert "2 records link to nothing yet" in page.locator(".gx-legend").inner_text()
    # The busiest record is a way in, not only a name.
    says.get_by_role("button", name=BUSIEST).click()
    assert page.locator(".gx-panel h2").inner_text() == BUSIEST
    assert not page.errors, page.errors
    page.close()


def test_the_sentence_follows_the_chinese_interface_and_a_translated_title_is_the_label(browser, built):
    page = open_graph(browser, built, language="zh")
    text = page.locator(".gx-says").inner_text()
    assert "5 个标签页" in text and "110 个人" in text and "最忙的是" in text
    labels = js(page, "() => graphState.labels.map(label => label.text)")
    assert "寒冷山谷里离网奶牛棚的储热" in labels
    assert "寒冷山谷里离网奶牛棚的储热" in page.locator(".gx-panel .gx-item b").all_inner_texts()
    page.close()


def test_labels_name_the_entries_and_the_most_linked_whole_words_and_never_on_a_mark(browser, built):
    page = open_graph(browser, built)
    drawn = js(page, """() => graphState.labels.map(label => ({ ...label, kind: GRAPH.byId.get(label.id).k,
      title: graphTitle(GRAPH.byId.get(label.id)), degree: graphDegree(GRAPH.byId.get(label.id)) }))""")
    entries = [label for label in drawn if label["kind"] == "knowledge"]
    others = [label for label in drawn if label["kind"] != "knowledge"]
    assert len(entries) == 5, "every knowledge entry is named"
    assert 4 <= len(others) <= 12, len(others)
    cut_off = js(page, "() => [...GRAPH.linked].filter(n => n.k !== 'knowledge').map(graphDegree).sort((a, b) => b - a)[11]")
    assert all(label["degree"] >= cut_off for label in others), "only the most linked are named"
    for label in drawn:
        text = label["text"]
        if not text.endswith("…"):
            assert text == label["title"], label
            continue
        kept = text[:-1]
        assert label["title"].startswith(kept) and label["title"][len(kept)] == " ", f"cut inside a word: {text!r}"
    # A whole entry title fits on two lines.
    assert next(label for label in entries if label["title"] == HEAT)["text"] == HEAT
    overlap = "(a, b) => a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1]"
    assert js(page, f"""() => {{ const hit = {overlap}, boxes = graphState.labels.map(label => label.box);
      return boxes.every((box, i) => boxes.every((other, j) => i === j || !hit(box, other))); }}"""), "labels overlap each other"
    on_marks = js(page, f"""() => {{ const hit = {overlap};
      return graphState.labels.flatMap(label => graphMarkBoxes().filter(mark => mark.id !== label.id && hit(label.box, mark.box)).map(mark => label.text + ' on ' + mark.id)); }}""")
    assert on_marks == [], on_marks
    # Zooming in names more of them.
    before = len(drawn)
    page.locator('.gx-zoom [data-zoom="1.4"]').click()
    page.locator('.gx-zoom [data-zoom="1.4"]').click()
    page.wait_for_timeout(500)
    assert js(page, "() => graphLabelBudget()") > 12
    assert before and not page.errors, page.errors
    page.close()


def test_pointing_at_a_mark_says_its_whole_name(browser, built):
    page = open_graph(browser, built)
    at = js(page, "id => { const n = GRAPH.byId.get(id), box = graphCanvas().getBoundingClientRect();"
                  " return [box.left + graphState.T.applyX(n.x), box.top + graphState.T.applyY(n.y)]; }", "knowledge/seed-lending.md")
    page.mouse.move(*at)
    assert page.locator(".gx-tip").inner_text().startswith("Seed-library lending rules and what a late return costs")
    page.close()


def test_the_panel_lists_whole_entry_titles_with_what_each_ties_together_and_is_no_taller_than_its_list(browser, built):
    page = open_graph(browser, built)
    panel = page.locator(".gx-panel")
    rows = panel.locator(".gx-item")
    assert rows.locator("b").all_inner_texts()[:5] == [
        HEAT, "Tide-table forecasting for small harbour pilots", "Seed-library lending rules and what a late return costs",
        "Lantern glass sourcing after the kiln cooperative closed", "Wool grading"]
    assert rows.locator("b").evaluate_all("names => names.every(b => b.scrollWidth <= b.clientWidth)"), "a title is cut"
    assert rows.first.locator("small").inner_text() == "15 people · 10 projects · 2 organisations"
    # It was a full-height card, two-thirds empty: now it ends where its list ends.
    assert js(page, "() => { const p = document.querySelector('.gx-panel'); return p.getBoundingClientRect().bottom - p.lastElementChild.lastElementChild.getBoundingClientRect().bottom; }") < 32
    # Selecting a mark: what the record is, in its own first sentence, then its links.
    rows.first.click()
    assert panel.locator("h2").inner_text() == HEAT
    assert panel.locator(".gx-summary").inner_text() == f"{HEAT} is what the valley learned the slow way."
    assert panel.locator(".gx-panel-body .gx-item").count() >= 10
    assert panel.locator(".gx-panel-body .gx-item b").evaluate_all("names => names.every(b => b.scrollWidth <= b.clientWidth)")
    page.close()


def test_no_saturated_colour_is_spent_on_a_navigation_button(browser, built):
    page = open_graph(browser, built, hash_="#view=graph&focus=knowledge%2Fheat-storage.md")
    link = page.locator(".gx-panel .gx-open")
    assert link.get_attribute("href") == "#r=knowledge%2Fheat-storage.md"
    green = js(page, "() => { const probe = document.body.appendChild(document.createElement('i')); probe.style.background = 'var(--green)';"
                     " const colour = getComputedStyle(probe).backgroundColor; probe.remove(); return colour; }")
    # The accent is ink now (#3144), and ink also draws the map's marks and labels: what must not wear it is a control.
    painted = js(page, "() => [...document.querySelectorAll('.gx-map :is(a, button, [role=button]), .gx-panel .gx-open')].map(node => getComputedStyle(node).backgroundColor)")
    assert green not in painted
    page.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_the_title_and_the_switch_do_not_move_between_graph_and_entries(browser, built, width):
    def head(hash_):
        page = open_graph(browser, built, width, hash_)
        found = js(page, """() => ['.knowledge-head h1', '.knowledge-switch'].map(selector => {
          const node = document.querySelector(selector), box = node.getBoundingClientRect(), style = getComputedStyle(node);
          return [Math.round(box.x), Math.round(box.y), Math.round(box.width), Math.round(box.height), style.fontSize, style.fontWeight, style.color]; })""")
        page.close()
        return found
    assert head("#c=knowledge") == head("#c=knowledge&view=entries")


def test_on_a_phone_the_map_is_the_entries_and_what_they_link_with_targets_a_thumb_can_hit(browser, built):
    page = open_graph(browser, built, 390)
    assert page.locator(".gx-map canvas").is_visible() and not page.locator(".gx-tabs").is_visible()
    shown = js(page, "() => GRAPH.linked.filter(graphVisible).map(n => n.id)")
    near = js(page, "() => GRAPH.linked.filter(n => n.k === 'knowledge' || [...GRAPH.adj.get(n.id)].some(id => GRAPH.byId.get(id).k === 'knowledge')).map(n => n.id)")
    assert sorted(shown) == sorted(near) and len(shown) < js(page, "() => GRAPH.linked.length")
    assert js(page, "() => graphState.focus") == "", "it opens on the whole simplified map, not on one entry"
    # Every entry is named, and its tap target is 44 px across whatever size it is drawn.
    assert len([text for text in js(page, "() => graphState.labels.map(label => label.id)") if text.startswith("knowledge/")]) == 5
    centres = js(page, "() => GRAPH.linked.filter(n => n.k === 'knowledge').map(n => { const box = graphCanvas().getBoundingClientRect();"
                       " return [n.id, box.left + graphState.T.applyX(n.x), box.top + graphState.T.applyY(n.y)]; })")
    for a in centres:
        for b in centres:
            assert a is b or ((a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** .5 >= 44, (a, b)
    tabbar = page.locator("#tabbar").bounding_box()
    canvas = page.locator(".gx-canvas").bounding_box()
    assert canvas["y"] + canvas["height"] <= tabbar["y"], "the map is whole above the tab bar"
    # With nothing selected the page is one screen: nothing is under the tab bar because nothing is below the map.
    assert not page.locator(".gx-panel").is_visible()
    assert js(page, "() => document.documentElement.scrollHeight <= innerHeight")
    name, x, y = centres[2]
    # A tap opens the record (#3095); Back returns to the map with that entry focused, its name and its way in
    # above the tab bar without scrolling.
    page.touchscreen.tap(x + 15, y - 15)
    page.wait_for_function("() => location.hash.startsWith('#r=')")
    assert js(page, "() => decodeURIComponent(location.hash.slice(3))") == name
    page.go_back()
    page.locator(".gx-map canvas").wait_for()
    assert js(page, "() => graphState.focus") == name
    for part in (".gx-panel h2", ".gx-panel .gx-open"):
        box = page.locator(part).bounding_box()
        assert box["y"] + box["height"] <= tabbar["y"], (part, box, tabbar)
    assert page.locator(".gx-panel .gx-open").bounding_box()["height"] >= 44
    assert page.locator(".gx-panel .gx-item").evaluate_all("rows => rows.every(row => row.getBoundingClientRect().height >= 44)")
    # Scrolled to the end, the last row is above the bar, and no list scrolls inside the page.
    js(page, "() => scrollTo(0, document.documentElement.scrollHeight)")
    page.wait_for_timeout(100)
    assert page.locator(".gx-panel").bounding_box()["y"] + page.locator(".gx-panel").bounding_box()["height"] <= tabbar["y"]
    assert js(page, "() => { const body = document.querySelector('.gx-panel-body'); return body.scrollHeight <= body.clientHeight + 1; }")
    assert js(page, "() => document.documentElement.scrollWidth <= innerWidth")
    assert not page.errors, page.errors
    page.close()


def test_a_click_opens_the_records_page_and_back_returns_to_the_same_mark_and_view(browser, built):
    """Owner, 2026-11-17 (#3095): opening something in the graph jumps to its page; pointing at it is the preview."""
    page = open_graph(browser, built)
    page.locator('.gx-zoom [data-zoom="1.4"]').click()
    page.wait_for_timeout(400)
    record = "projects/quarry-open-day.md"
    at = js(page, "id => { const n = GRAPH.byId.get(id), box = graphCanvas().getBoundingClientRect();"
                  " return [box.left + graphState.T.applyX(n.x), box.top + graphState.T.applyY(n.y)]; }", record)
    view = js(page, "() => [graphState.T.k, graphState.T.x, graphState.T.y]")
    # Pointing previews it in the panel: its name, its first sentence, its links; nothing else moves.
    page.mouse.move(*at)
    page.locator(".gx-panel h2").wait_for()
    assert page.locator(".gx-panel h2").inner_text() == "Quarry open day"
    assert page.locator(".gx-panel .gx-summary").inner_text() == "Quarry open day is one of the valley's shared works."
    assert js(page, "() => location.hash") == "#c=knowledge" and js(page, "() => [graphState.T.k, graphState.T.x, graphState.T.y]") == view
    page.mouse.click(*at)
    page.wait_for_function("() => location.hash === '#r=projects%2Fquarry-open-day.md'")
    # The record renders after the hash changes (its page states are read first); wait for it, then compare.
    page.wait_for_function("() => document.querySelector('#main h1')?.innerText === 'Quarry open day'")
    page.go_back()
    page.locator(".gx-map canvas").wait_for()
    assert js(page, "() => location.hash") == "#view=graph&focus=projects%2Fquarry-open-day.md"
    assert js(page, "() => graphState.focus") == record
    assert js(page, "() => [graphState.T.k, graphState.T.x, graphState.T.y]") == view, "the pan and zoom he left"
    assert page.locator(".gx-panel h2").inner_text() == "Quarry open day"
    # Enter on the focused mark opens it too; a click on empty paper lets go of the focus.
    page.locator(".gx-canvas").focus()
    page.keyboard.press("Enter")
    page.wait_for_function("() => location.hash === '#r=projects%2Fquarry-open-day.md'")
    page.go_back()
    page.locator(".gx-map canvas").wait_for()
    box = page.locator(".gx-canvas").bounding_box()
    page.mouse.click(box["x"] + 6, box["y"] + 6)
    assert js(page, "() => graphState.focus") == ""
    assert not page.errors, page.errors
    page.close()
