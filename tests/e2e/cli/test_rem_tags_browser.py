"""Tags in the reader (#3093): one vocabulary over every page, a page per tag, filters on every list, tag: in search,
tag nodes in the graph, and close-all-by-tag in the open items. The notebook is the invented one in
tests/fixtures/rem_reader_notebook.py, with Tags lines written the way the tag stage writes them."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
SHOTS = Path(os.environ.get("REM_PR_SHOTS", "/tmp/rem-tags-shots"))
TAGGED = {"people/mara-ostrowski.md": [("pilot", "1"), ("client", "")],
          "people/tomas-reyes.md": [("pilot", "")],
          "orgs/fernhill-labs.md": [("pilot", "")],
          "projects/harbour.md": [("pilot", "")]}
DECISION = "# Keep one vocabulary for every kind\n\nTags come from one list [1].\n\n## Sources\n- [1] codex:fixture:1 — 2026-09-03\n"


def _notebook(root, now):
    from rem_reader_notebook import build
    from connectonion.rem import tags
    from connectonion.rem.files import Notebook, state_path, write_json
    build(root, now)
    book = Notebook(root)
    for path, rows in TAGGED.items():
        book.write(path, tags.with_tags(book.read(path), [{"tag": slug, "citation": cite} for slug, cite in rows]))
    book.write("decisions/one-vocabulary.md", tags.with_tags(DECISION, [{"tag": "pilot", "citation": "1"}]))
    write_json(state_path(root, "tags.json"), {"tags": {"pilot": {"label": "Fernhill pilot", "kind": "project", "aliases": ["fernhill-pilot"]}}})
    return root


@pytest.fixture
def reader(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    html = rem_reader.render(_notebook(tmp_path / "rem", datetime(2026, 10, 1, 12, tzinfo=timezone.utc)), local=True)
    calls, errors = [], []

    def serve(route):
        path = route.request.url[len(BASE) - 1:].split("#")[0]
        if path.startswith("/rem/"):
            calls.append((path, json.loads(route.request.post_data or "{}")))
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

        def open_page(hash_, width=1440, language="zh"):
            page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
            page.evaluate("""([hash, language]) => { setInterfaceLanguage(language); location.hash = hash; render(); }""",
                          [hash_, language], isolated_context=False)
            page.locator("#main h1, #main canvas").first.wait_for()
            return page

        yield open_page, calls
        browser.close()
    assert not errors, errors


def _shot(page, name, width):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"tags-{name}-{width}.png"))
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_a_tag_has_its_page_and_search_finds_it_by_slug_label_or_alias(reader, width):
    open_page, _ = reader
    page = open_page("q=" + "tag%3Afernhill-pilot", width)  # an alias resolves to its tag
    assert page.locator("#main h1").inner_text() == "Fernhill pilot"
    assert "5 页带这个标签" in page.locator("#main .lede").inner_text()
    groups = page.locator("#main .tag-group")
    assert groups.count() == 4  # people, organisations, projects, decisions
    assert "Keep one vocabulary for every kind" in page.locator("#main").inner_text()
    _shot(page, "page", width)
    # A plain word that is a tag offers its page above the text matches.
    page = open_page("q=pilot", width)
    hit = page.locator("#main .tag-hit a")
    assert hit.count() == 1 and "Fernhill pilot" in hit.inner_text()
    hit.click()
    page.wait_for_function("() => decodeURIComponent(location.hash) === '#q=tag:pilot'")


@pytest.mark.parametrize("width", [1440, 390])
def test_a_persons_tags_are_words_that_open_their_tag_page(reader, width):
    open_page, _ = reader
    page = open_page("r=people%2Fmara-ostrowski.md", width)
    row = page.locator(".person-head .pcard .pc-row", has=page.locator(".pc-k", has_text="标签"))
    assert row.count() == 1
    link = row.locator("a.tag-link")
    assert link.all_inner_texts() == ["Fernhill pilot", "client"]  # labels, in page order; client is a starter role
    link.first.click()
    page.wait_for_function("() => decodeURIComponent(location.hash) === '#q=tag:pilot'")


@pytest.mark.parametrize("width", [1440, 390])
def test_a_list_filters_by_tag_and_a_second_tap_clears_it(reader, width):
    open_page, _ = reader
    page = open_page("c=people", width)
    bar = page.locator("#main .tag-bar")
    assert bar.count() == 1
    # Under the heading, above the rows it filters.
    assert bar.bounding_box()["y"] < page.locator("#main table, #main ul, #main .ov-list").first.bounding_box()["y"]
    chip = bar.locator("a.chip", has_text="Fernhill pilot")
    assert chip.locator(".chip-n").inner_text() == "2"
    chip.click()
    page.wait_for_function("() => location.hash.includes('tag=pilot')")
    page.evaluate("render()", isolated_context=False)
    text = page.locator("#main").inner_text()
    assert "Mara Ostrowski" in text and "Tomás Reyes" in text and "Inès Halvorsen" not in text
    _shot(page, "people-filtered", width)
    page.locator("#main .tag-bar a.chip.on").click()
    page.wait_for_function("() => !location.hash.includes('tag=')")


def test_each_tag_is_a_node_in_the_graph_linked_to_its_pages(reader):
    open_page, _ = reader
    page = open_page("view=graph", 1440, "en")
    model = page.evaluate("""() => { const m = graphModel(); const tag = m.byId.get('tag:pilot');
      return tag && { kind: tag.k, label: graphTitle(tag), links: [...m.adj.get('tag:pilot')].sort() }; }""", isolated_context=False)
    assert model and model["kind"] == "tags" and model["label"] == "Fernhill pilot"
    assert "people/mara-ostrowski.md" in model["links"] and "orgs/fernhill-labs.md" in model["links"]
    page.locator(".gx-tabs [data-tab=tags], [data-tab=tags]").first.click()
    _shot(page, "graph", 1440)


def test_the_open_items_filter_by_a_page_tag_and_close_all_of_them(reader):
    open_page, _ = reader
    page = open_page("view=open", 1440, "en")
    chip = page.locator("#main .open-chips a.chip", has_text="Fernhill pilot")
    assert chip.count() == 1
    chip.click()
    page.wait_for_function("() => location.hash.includes('tag=tag%3Apilot')")
    page.evaluate("() => { REM.live = true; render(); }", isolated_context=False)  # closing is the live reader's
    done = page.locator("#main .bulk-bar .bulk-done")
    assert done.is_visible()
    n = int("".join(ch for ch in done.inner_text() if ch.isdigit()))
    rows = page.locator("#main ul.threads > li").count()
    assert n == rows >= 1  # every row the filter shows, and only those
    _shot(page, "open-filtered", 1440)
    done.click()
    page.wait_for_function("() => document.querySelectorAll('#main ul.threads > li').length === 0 || document.querySelector('.done-notice, [role=status]')")
