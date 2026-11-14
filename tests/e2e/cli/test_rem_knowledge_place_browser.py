"""One Knowledge place, and pages that show instead of explain (opt in with CO_REM_BROWSER_TEST=1).

Owner, 2026-11-13 (#2996): «为什么会有"知识"和"全部记录"这两个？"全部记录"那个你就不要了……"知识"应该是按照
Wiki 拆开的每一个东西». The rail keeps one Knowledge place; the graph that All records drew is one switch away
inside it, and every record the All records list held stays in its own category and in search.

Owner, 2026-11-13 (#2994): «上面还有大字写着"什么是最常见的什么"，那个文字根本不重要……不要写字告诉我，要让我
通过 UI 之类就能一目了然地判断出来». The sentences that described a page's order are gone; the order stays.

The notebook is the invented one in tests/fixtures plus one topic its project names.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

RAIL = ["#", "#view=open", "#c=people", "#c=orgs", "#c=projects", "#c=skills", "#c=knowledge"]


def notebook(root):
    from rem_reader_notebook import build
    from connectonion.rem.files import Notebook
    build(root, datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
    nb = Notebook(root)
    nb.write("principles/steady.md", "# Steady pace\n\nKeep a steady pace.\n")
    nb.write("orgs/fable.md", "# Fable Research Cooperative\n\nStudies Heat storage.\n")
    nb.stub_topic("knowledge/heat-storage.md", "Heat storage", ["Heat storage", "thermal battery"])
    nb.write("projects/cove.md", "# Cove\n## What it is\n- Cove sells heat storage to farms. [1]\n\n"
             "## Sources\n- [1] gmail:c1 — 2026-01-10 — Cove\n")
    return root


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from connectonion.rem.reader import render
    tmp = tmp_path_factory.mktemp("knowledge")
    path = tmp / "reader.html"
    path.write_text(render(notebook(tmp / "rem"), local=True), encoding="utf-8")
    return path.as_uri()


@pytest.fixture
def browser():
    from patchright.sync_api import sync_playwright
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        yield browser
        browser.close()


def open_page(browser, uri, width=1440, language="en"):
    page = browser.new_page(viewport={"width": width, "height": 900 if width > 400 else 844}, locale="en-US")
    page.errors = []
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    page.route("http*://**/*", lambda route: route.abort())
    page.goto(uri)
    page.locator("#nav a").first.wait_for(state="attached")
    if language != "en":
        page.evaluate("language => setInterfaceLanguage(language)", language, isolated_context=False)
    return page


def go(page, hash_):
    page.evaluate("hash => { location.hash = hash; }", hash_)
    page.wait_for_timeout(150)


@pytest.mark.parametrize("width", [1440, 390])
def test_the_rail_has_one_knowledge_place_and_no_all_records(browser, built, width):
    for language, gone in (("en", "All records"), ("zh", "全部记录")):
        page = open_page(browser, built, width, language)
        if width < 400:
            page.locator("#tabbar .nav-toggle").click()  # the phone sheet is the rail
        assert page.locator("#nav > a").evaluate_all("links => links.map(a => a.getAttribute('href'))") == RAIL
        names = page.locator("#nav").evaluate("nav => [...nav.querySelectorAll('[data-name]')].map(n => n.dataset.name).join('|')")
        assert gone not in names and gone not in page.locator("#nav").inner_text()
        assert page.locator('#nav a[href="#c=all"]').count() == 0
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not page.errors, page.errors
        page.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_knowledge_holds_its_entries_and_the_graph_that_all_records_drew(browser, built, width):
    page = open_page(browser, built, width)
    go(page, "#c=knowledge")
    page.locator(".gx-topics .gx-rows li").first.wait_for()
    entry = page.locator(".gx-rows li").first
    assert entry.locator("b").inner_text() == "Heat storage"
    # A wiki entry shows what it links to: the project that names it is one tap from the list.
    assert entry.locator('a[href="#r=projects%2Fcove.md"]').count() == 1
    if width < 400:
        title = entry.locator('.gx-entry').bounding_box()
        assert title['width'] >= 250, title
        assert entry.locator('.gx-entry-links a').evaluate_all(
            "links => links.every(a => a.getBoundingClientRect().right <= innerWidth)")
    # A sparse wiki offers the existing linked records without inventing more topics.
    assert page.locator('.gx-topics > .gx-quiet-line a[href="#view=graph"]').inner_text() == "Explore linked records →"
    switch = page.locator(".knowledge-switch")
    assert switch.locator("a").all_inner_texts() == ["Entries", "Graph"]
    assert switch.locator('a[aria-current="page"]').inner_text() == "Entries"
    switch.get_by_role("link", name="Graph").click()
    page.locator(".gx-map canvas").wait_for()
    assert page.evaluate("location.hash") == "#view=graph"
    assert page.locator("#nav a.active").get_attribute("href") == "#c=knowledge"
    assert page.title() == "Knowledge · co rem"
    assert page.locator('.knowledge-switch a[aria-current="page"]').inner_text() == "Graph"
    # The old All records address is a bookmark someone kept: it opens the same graph, under Knowledge.
    go(page, "#c=all")
    page.locator(".gx-map canvas").wait_for()
    assert page.locator("#nav a.active").get_attribute("href") == "#c=knowledge"
    assert page.locator(".all-switch").count() == 0
    go(page, "#r=knowledge%2Fheat-storage.md")
    assert page.locator("#nav a.active").get_attribute("href") == "#c=knowledge"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not page.errors, page.errors
    page.close()


def test_what_only_all_records_reached_is_reachable_from_knowledge_or_search(browser, built):
    page = open_page(browser, built)
    labels = page.evaluate("paletteItems().map(item => item.label)", isolated_context=False)
    assert "Open Graph" in labels and "Open Knowledge" in labels and "Open All records" not in labels
    # The All records list was every listed record; each one still sits in a rail place or under 更多.
    page.locator(".nav.more").click()
    unplaced = page.evaluate("""() => {
      const places = new Set([...document.querySelectorAll('#nav a[href^="#c="], #rail-more a[href^="#c="]')].map(a => a.getAttribute('href').slice(3)));
      return listedRecords().filter(r => !places.has(r.category)).map(r => r.path);
    }""", isolated_context=False)
    assert unplaced == []
    go(page, "#q=Cove")
    assert page.locator('#main a[href="#r=projects%2Fcove.md"]').count() >= 1
    go(page, "#q=Steady%20pace")
    isolated = page.locator('#main a[href="#r=principles%2Fsteady.md"]')
    assert isolated.count() == 1  # no graph edge is needed for a record to remain reachable
    isolated.click()
    assert page.locator('#main h1').inner_text() == "Steady pace"
    page.close()


@pytest.mark.parametrize("language", ["en", "zh"])
def test_pages_lose_the_sentences_that_explained_their_order(browser, built, language):
    gone = {
        "#c=skills": ["What your agents can do", "Most used", "Everything they can do", "Contents\n", "你的 agent 会做的事",
                      "最常用", "全部能力", "目录"],
        "#": ["Start with this", "Start with these", "先看这"],
        "#c=knowledge": ["Subjects that tie your records together", "knowledge entr", "See them in the graph",
                         "把记录串起来的知识", "条知识", "在图谱里看"],
        "#view=graph": ["records linked together", "Whole map", "Click a point to see what it connects", "Most connected",
                        "条记录连在一起", "整张图", "点一个点", "连接最多", "All records", "全部记录"],
        "#c=sessions": ["What you worked on with your coding agents", "和编程 agent 一起做的事"],
        "#c=projects": ["Sorted by health; a sub-project sits under its project", "按健康排列；子项目缩在它的项目下"],
        "#c=projects&v=board": ["The board's axis is a question:", "看板的轴是一个问题："],
        "#c=people": ["Who is this, and where did we leave off?", "这是谁？上次聊到哪了？", "Contents\n"],
        "#c=orgs": ["Companies, teams, and groups we correspond with", "有往来的公司、团队与组织", "Contents\n"],
        "#c=agenda": ["Promises, waiting on others, dates that matter", "承诺、等待对方的事项与重要日期", "Contents\n"],
        "#c=opportunities": ["Worth exploring, not yet committed", "值得探索，尚未决定投入", "Contents\n"],
        "#c=principles": ["Standing rules we adopted", "已采用的长期原则", "Contents\n"],
        "#c=works": ["Outputs that can be reused or shown", "可复用或展示的成果", "Contents\n"],
        "#c=decisions": ["What we chose and why", "做了什么决定，为什么", "Category", "分类"],
    }
    page = open_page(browser, built, 1440, language)
    for hash_, sentences in gone.items():
        go(page, hash_)
        page.wait_for_timeout(200)
        text = page.locator("#main").inner_text()
        for sentence in sentences:
            assert sentence not in text, (hash_, sentence)
    # Most used still leads, as cards, and the first one sits near the top of the first screen.
    go(page, "#c=skills")
    first = page.locator(".skills-top .skill-card").first.bounding_box()
    assert first["y"] < 200, first
    assert page.locator(".skills-top .skill-card").count() >= 1
    # The page still names itself.
    assert page.locator("#main h1").inner_text() == ("技能" if language == "zh" else "Skills")
    assert not page.errors, page.errors
    page.close()
