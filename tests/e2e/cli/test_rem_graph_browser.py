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


def test_the_graph_is_reached_from_the_sidebar_and_search_focuses_a_topic(page):
    page, uri = page
    page.get_by_role("link", name="Graph", exact=True).click()
    page.locator(".gx-map canvas").wait_for()
    assert "4 records linked together" in page.locator(".gx-title").inner_text()
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
    page.locator(".language-switch button[lang=zh]").click()
    page.goto(uri + "#view=graph")
    page.locator(".gx-title").wait_for()
    assert "4 条记录连在一起" in page.locator(".gx-title").inner_text()


def test_with_no_topics_the_rail_leaves_them_out_and_the_page_names_the_command(tmp_path, monkeypatch):
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
            assert page.locator('#nav a[href="#c=knowledge"]').count() == 0
            page.goto(path.as_uri() + "#c=knowledge")
            page.locator(".gx-filed code").wait_for()
            assert page.locator(".gx-filed code").inner_text().endswith(" backfill topics --propose")  # --root: not the default notebook
            assert page.locator(".gx-topics .gx-rows").count() == 0  # no rule under an empty list
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.close()
        browser.close()
