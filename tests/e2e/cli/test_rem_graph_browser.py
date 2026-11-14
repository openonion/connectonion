"""The graph and a topic page in a real browser (opt in with CO_REM_BROWSER_TEST=1).

An invented notebook: a topic stub that REM has not written yet, two people and a
project whose cited sentences name it, and a person who only shares the word.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)

TOPIC = "knowledge/heat-storage.md"


def notebook(root):
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    prepare(root)
    nb = Notebook(root)
    nb.stub_topic(TOPIC, "Heat storage", ["Heat storage", "thermal battery"])
    nb.write("people/mara-ostrowski.md", "# Mara Ostrowski\n## Facts\n- Role: Farm engineer\n\n## Insight\n"
             "- Mara is building a thermal battery for the Cove barns. [1]\n\n## Sources\n- [1] gmail:m1 — 2026-02-03 — Mara\n")
    nb.write("people/quinn-alder.md", "# Quinn Alder\n## Insight\n- Quinn priced heat storage for the dairy. [1]\n"
             "- Quinn works with [Mara Ostrowski](mara-ostrowski.md). [1]\n\n## Sources\n- [1] gmail:q1 — 2026-01-12 — Quinn\n")
    nb.write("projects/cove.md", "# Cove\n## What it is\n- Cove sells heat storage to farms. [1]\n\n## Sources\n- [1] gmail:c1 — 2026-01-10 — Cove\n")
    nb.write("people/ellis-park.md", "# Ellis Park\nEllis once said heat storage at a dinner.\n")
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


def test_knowledge_opens_the_graph_and_search_focuses_a_knowledge_entry(page):
    page, uri = page
    page.locator('#nav a[href="#c=knowledge"]').click()
    page.locator(".knowledge-switch").get_by_role("link", name="Graph").click()
    page.locator(".gx-map canvas").wait_for()
    assert "Knowledge 1" in page.locator(".gx-legend").inner_text()  # the counts are the legend's, not a heading
    assert page.locator(".gx-panel .gx-open").count() == 0  # the whole map has no green action
    page.locator(".gx-search").fill("thermal")
    page.locator(".gx-results li").first.click()
    assert "focus=knowledge%2Fheat-storage.md" in page.url
    panel = page.locator(".gx-panel")
    assert panel.locator("h2").inner_text() == "Heat storage"
    assert panel.locator(".gx-open").count() == 1
    assert panel.locator(".gx-open").get_attribute("href") == "#r=knowledge%2Fheat-storage.md"
    assert {"Mara Ostrowski", "Quinn Alder", "Cove"} <= set(panel.locator(".gx-item b").all_inner_texts())
    assert "Ellis Park" not in panel.inner_text()  # a shared word is not a link
    # The canvas draws something: the focused topic's pixels are not blank.
    assert page.evaluate("""() => { const c = document.querySelector('.gx-map canvas');
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
      for (let i = 3; i < d.length; i += 4) if (d[i]) return true; return false; }""")


def test_a_topic_page_is_a_record_with_cited_sentences_and_a_local_graph(page):
    page, uri = page
    for width, theme in ((1440, "light"), (390, "dark")):
        page.set_viewport_size({"width": width, "height": 900})
        page.emulate_media(color_scheme=theme)
        page.goto(uri + "#r=knowledge%2Fheat-storage.md")
        page.locator(".gx-topic h1").wait_for()
        assert page.locator(".gx-topic h1").inner_text() == "Heat storage"
        assert "REM has not written this page yet" in page.locator(".gx-topic .gx-lede").inner_text()
        rows = page.locator(".gx-link-row")
        names = page.locator(".gx-sec").first.locator(".gx-row-name a").all_inner_texts()
        assert names == ["Mara Ostrowski", "Quinn Alder", "Cove"]
        assert "thermal battery" in rows.first.locator("b").inner_text()
        assert "Mara is building a thermal battery" in rows.first.inner_text()
        assert "Ellis Park" in page.locator(".gx-sec", has_text="Maybe related").inner_text()
        assert page.locator(".gx-rail .gx-local-svg a:not(.centre)").count() == 3
        assert page.locator(".gx-local-foot a").get_attribute("href") == "#view=graph&focus=knowledge%2Fheat-storage.md"
        assert page.locator(".gx-topic .gx-open, .gx-topic .btn-act").count() == 0  # a record, not a to-do
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_person_and_project_pages_carry_a_local_graph_and_their_topics(page):
    page, uri = page
    page.goto(uri + "#r=people%2Fquinn-alder.md")
    block = page.locator(".gx-attach")
    block.wait_for()
    assert block.locator(".gx-local-svg a:not(.centre)").count() == 2
    assert block.locator(".gx-topic-line a").inner_text() == "Heat storage"
    page.goto(uri + "#r=projects%2Fcove.md")
    assert page.locator(".gx-attach .gx-topic-line a").inner_text() == "Heat storage"


def test_the_topic_list_and_graph_follow_the_chinese_interface(page):
    page, uri = page
    page.goto(uri + "#c=knowledge")
    page.locator(".gx-topics").wait_for()
    assert page.locator(".gx-rows li").count() == 1
    page.locator(".settings-open").click()
    page.locator(".language-switch button[lang=zh]").click()
    page.keyboard.press("Escape")
    assert page.locator(".gx-topics h1").inner_text() == "知识"
    assert page.title() == "知识 · co rem"
    page.goto(uri + "#view=graph")
    page.locator(".gx-map canvas").wait_for()
    assert page.locator(".gx-map h1").inner_text() == "知识"
    assert page.locator(".knowledge-switch").inner_text().split() == ["条目", "图谱"]


def test_with_no_topics_knowledge_says_rem_files_them_at_night(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    from connectonion.rem.reader import render
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).write("people/quinn-alder.md", "# Quinn Alder\n## Insight\n- Quinn priced heat storage. [1]\n\n## Sources\n- [1] gmail:q1 — 2026-01-12 — Quinn\n")
    path = tmp_path / "reader.html"
    path.write_text(render(root, local=True), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        for width in (1440, 390):
            page = browser.new_page(viewport={"width": width, "height": 900}, locale="en-US")
            page.goto(path.as_uri())
            page.locator("#nav a").first.wait_for(state="attached")  # behind a menu at 390
            # #2996: Knowledge is a rail place even before the night files an entry; it holds the graph too.
            assert page.locator('#nav > a[href="#c=knowledge"]').count() == 1
            page.goto(path.as_uri() + "#c=knowledge")
            page.locator(".gx-filed").wait_for()
            # D-60 (#2910): REM files knowledge itself on its night run; no command to copy.
            assert page.locator(".gx-filed").inner_text() == "REM files knowledge from your records on its night run."
            assert page.locator("#main code, #main .cmd").count() == 0
            assert page.locator(".gx-topics .gx-rows").count() == 0  # no rule under an empty list
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.close()
        browser.close()


def test_the_rail_has_no_graph_entry_and_knowledge_comes_last(page):
    """Owner, 2026-11-09: "我之前不是说了那个 graph，为什么要又有一个新的 graph 呢？" """
    page, uri = page
    labels = [text.split("\n")[0] for text in page.locator("#nav a").all_inner_texts()]
    assert "Graph" not in labels and "Topics" not in labels and "All" not in labels
    # #2996: Knowledge ends the rail's places and holds the graph; the rest of memory waits behind 更多.
    assert page.locator("#nav > a").evaluate_all("links => links.map(a => a.getAttribute('href'))")[-1] == "#c=knowledge"
    # Activity was the team's invention (D-03): REM's run history is reached from Memory changes only.
    assert page.locator('.rail a[href="#view=activity"]').count() == 0
    page.locator('.nav.more').click()
    page.locator('#nav a[href="#view=changes"]').click()
    activity = page.locator('#main a[href="#view=activity"]', has_text="REM activity")
    assert activity.inner_text() == "REM activity →"
    activity.click()
    page.get_by_role("heading", name="Activity", exact=True).wait_for()


def test_knowledge_switches_between_its_entries_and_the_graph(page):
    page, uri = page
    page.goto(uri + "#c=all")  # All records' old address, kept as a bookmark, opens the graph under Knowledge
    page.locator(".gx-map canvas").wait_for()
    assert page.title() == "Knowledge · co rem"
    assert page.locator('#nav a.active').get_attribute("href") == "#c=knowledge"
    switch = page.locator(".knowledge-switch")
    assert switch.locator('[aria-current="page"]').inner_text() == "Graph"
    switch.get_by_role("link", name="Entries").click()
    page.locator(".gx-topics .gx-rows").wait_for()
    assert page.locator(".gx-map").count() == 0
    assert page.locator('.knowledge-switch [aria-current="page"]').inner_text() == "Entries"
    page.goto(uri + "#view=graph&focus=knowledge%2Fheat-storage.md")
    page.locator(".gx-map canvas").wait_for()
    assert page.locator('#nav a.active').get_attribute("href") == "#c=knowledge"
    assert page.locator(".gx-panel h2").inner_text() == "Heat storage"


def test_a_knowledge_entry_keeps_the_knowledge_name_in_its_crumb_and_title(page):
    page, uri = page
    page.goto(uri + "#r=knowledge%2Fheat-storage.md")
    assert page.locator(".gx-crumb").inner_text() == "Knowledge"
    page.goto(uri + "#c=knowledge")
    assert page.locator(".gx-topics h1").inner_text() == "Knowledge"
    assert page.locator(".gx-rows li").count() == 1  # the list counts itself; no "1 knowledge entry" heading
    assert page.title() == "Knowledge · co rem"


def test_the_map_never_draws_over_its_own_heading_tabs_or_legend(page):
    # The canvas once filled the whole map under a see-through heading: a node sat on the
    # Projects tab and another on the title. The map is drawn between the heading and the legend.
    page, uri = page
    for width in (1440, 390):
        page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
        page.goto(uri + "#view=graph")
        page.locator(".gx-map canvas").wait_for()
        canvas = page.locator(".gx-map canvas").bounding_box()
        for selector in (".gx-head .knowledge-head", ".gx-bar", ".gx-tabs"):
            box = page.locator(selector).bounding_box()
            assert canvas["y"] >= box["y"] + box["height"], (width, selector, canvas, box)
        if width > 720:
            for selector in (".gx-legend", ".gx-zoom"):
                box = page.locator(selector).bounding_box()
                assert canvas["y"] + canvas["height"] <= box["y"], (width, selector, canvas, box)
        # Fitted, every point sits inside the canvas it is drawn on.
        assert page.evaluate("""() => GRAPH.linked.filter(graphVisible).every(n => {
          const x = graphState.T.applyX(n.x), y = graphState.T.applyY(n.y);
          return x >= 0 && x <= graphState.W && y >= 0 && y <= graphState.H; })""", isolated_context=False)
