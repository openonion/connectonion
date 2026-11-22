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
          "projects/harbour.md": [("pilot", "")],
          "skills/catalog/weekly-brief.md": [("pilot", ""), ("harbour", "")]}
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
    write_json(state_path(root, "tags.json"), {"tags": {"pilot": {"label": "Fernhill pilot", "kind": "project", "aliases": ["fernhill-pilot"]},
                                                        "harbour": {"label": "Harbour", "kind": "project", "aliases": []}}})
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
    assert "6 页带这个标签" in page.locator("#main .lede").inner_text()
    groups = page.locator("#main .tag-group")
    assert groups.count() == 5  # people, organisations, projects, skills, decisions
    assert "Keep one vocabulary for every kind" in page.locator("#main").inner_text()
    _shot(page, "page", width)
    # A plain word that is a tag offers its page above the text matches.
    page = open_page("q=pilot", width)
    hit = page.locator("#main .tag-hit a")
    assert hit.count() == 1 and "Fernhill pilot" in hit.inner_text()
    hit.click()
    page.wait_for_function("() => decodeURIComponent(location.hash) === '#q=tag:pilot'")


@pytest.mark.parametrize("width", [1440, 390])
def test_a_persons_tags_are_chips_that_open_their_tag_page(reader, width):
    open_page, _ = reader
    page = open_page("r=people%2Fmara-ostrowski.md", width)
    # The head's tag row, as on every record (rc35 hunt, #3131); the profile card no longer repeats it.
    row = page.locator(".person-head .page-tags")
    assert row.count() == 1 and page.locator(".person-head .pcard .pc-k", has_text="标签").count() == 0
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


def test_the_knowledge_graph_draws_only_pages_and_a_tag_links_to_its_page(reader):
    """#3140: one kind of point, the page. No tag points, no hexagons, no Tags tab; a tag chip opens its page."""
    open_page, _ = reader
    page = open_page("view=graph", 1440, "en")
    kinds = page.evaluate("() => [...new Set(graphModel().nodes.map(n => n.k))]", isolated_context=False)
    assert "tags" not in kinds
    assert page.locator(".gx-tabs [data-tab=tags], [data-tab=tags]").count() == 0
    _shot(page, "graph", 1440)
    # A tag named for a page opens that page: link 'pilot' to the project page and follow a chip. (Not her own
    # organisation: the head already links that, so its tag is not repeated, rc35 hunt / #3131.)
    page = open_page("r=people%2Fmara-ostrowski.md", 1440)
    page.evaluate("() => { REM.tags.pilot.page = 'projects/harbour.md'; render(); }", isolated_context=False)
    chip = page.locator(".person-head a", has_text="Fernhill pilot").first
    assert chip.get_attribute("href") == "#r=projects%2Fharbour.md"


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


@pytest.mark.parametrize("width", [1440, 390])
def test_a_tag_page_shows_what_rem_wrote_above_the_pages_that_carry_it(reader, width):
    """#3140 (`co rem tag`): the tag's written page (knowledge/<tag>.md) leads its 标签页, without its member list or
    Sources, and is not listed among its own members."""
    open_page, _ = reader
    page = open_page("q=tag%3Apilot", width)
    page.evaluate("""() => {
      REM.records.push({ path: 'knowledge/pilot.md', title: 'Fernhill pilot', category: 'knowledge', written: true, tags: ['pilot'],
        text: '# Fernhill pilot\\n- Tags: pilot\\n\\nThe pilot is Fernhill\\'s three-seat trial of the notebook [1].\\n\\n## Timeline\\n- 2026-08-22: the pilot was agreed [1].\\n\\n## Pages\\n- [Mara](../people/mara-ostrowski.md)\\n\\n## Sources\\n- [1] gmail:fixture:1\\n' });
      KNOWN.clear(); render();
    }""", isolated_context=False)
    written = page.locator("#main .tag-written")
    written.wait_for()
    text = written.inner_text()
    # The date reads in its sentence's language and never as ISO (#3194): an English line says "Aug 22" in either interface.
    assert "three-seat trial" in text and "Aug 22" in text and "2026-08-22" not in text
    assert "gmail:fixture:1" not in text and "Pages" not in text  # code's parts stay off the face
    assert written.get_by_role("link", name="打开标签页 →").get_attribute("href").endswith("knowledge%2Fpilot.md")
    box, groups = written.bounding_box(), page.locator("#main .tag-group").first.bounding_box()
    assert box["y"] < groups["y"]  # what it is, then its pages
    assert "knowledge/pilot.md" not in [a.get_attribute("href") for a in page.locator("#main .tag-group a").all()]
    _shot(page, "written-page", width)


def test_the_whole_network_is_called_the_knowledge_graph(reader):
    open_page, _ = reader
    page = open_page("view=graph")
    assert "知识图谱" in page.locator(".knowledge-switch").inner_text()
    page = open_page("view=graph", language="en")
    assert "Knowledge graph" in page.locator(".knowledge-switch").inner_text()


@pytest.mark.parametrize("width", [1440, 390])
def test_a_tag_page_has_the_investigate_button_with_why_it_is_due(reader, width):
    """#3140: a tag page is investigated like any page. Its head carries the same control (#3105); the line under it
    says how many pages carrying the tag are new or changed, and a click asks the host to investigate that page."""
    open_page, calls = reader
    page = open_page("q=tag%3Apilot", width)
    page.evaluate("""() => {
      REM.live = true;
      REM.records.push({ path: 'knowledge/pilot.md', title: 'Fernhill pilot', category: 'knowledge', written: true, tags: ['pilot'],
        text: '# Fernhill pilot\\n- Tags: pilot\\n\\nThe pilot is Fernhill\\'s three-seat trial of the notebook [1].\\n\\n## Pages\\n- [Mara](../people/mara-ostrowski.md)\\n\\nInvestigation: investigated 2026-09-01 (tag page, from 4 pages)\\n\\n## Sources\\n- [1] gmail:fixture:1\\n',
        investigation: { label: 'update', last: '2026-09-01', new_pages: 2, new_mails: 0, new_sessions: 0, leads: 0, cost: { quick: null, full: null } } });
      KNOWN.clear(); location.hash = '#r=knowledge%2Fpilot.md'; render();
    }""", isolated_context=False)
    control = page.locator("#main .gx-topic-head .inv")
    control.wait_for()
    assert "有 2 个带这个标签的页面是新的或改过" in control.inner_text()
    assert control.locator(".inv-go").inner_text() == "调查"
    assert control.locator(".inv-go").evaluate("b => getComputedStyle(b).backgroundColor") not in ("rgba(0, 0, 0, 0)", "transparent")
    _shot(page, "investigate-button", width)
    assert page.evaluate("liveHere()", isolated_context=False)
    control.locator(".inv-go").click()
    for _ in range(50):
        if any(path == "/rem/investigate" for path, _ in calls):
            break
        page.wait_for_timeout(100)
    assert ("/rem/investigate", {"action": "run", "page": "knowledge/pilot.md", "mode": "full"}) in calls


@pytest.mark.parametrize("path", ["decisions/one-vocabulary.md", "orgs/fernhill-labs.md", "projects/harbour.md",
                                  "skills/catalog/weekly-brief.md"])
def test_every_page_kind_shows_its_tags_under_its_title_and_a_chip_opens_the_right_page(reader, path):
    """Owner, 2026-11-19: every page kind shows its own tags in its header, one shared row. A chip opens the page the
    tag names (the skill's "Harbour" opens the Harbour project) or, for a tag no page is named for, the tag's page."""
    open_page, _ = reader
    page = open_page("r=" + path.replace("/", "%2F"))
    row = page.locator("#main .page-tags").first
    row.wait_for()
    assert row.locator(".page-tags-label").inner_text() == "标签"
    pilot = row.get_by_role("link", name="Fernhill pilot")
    assert pilot.get_attribute("href") == "#q=tag%3Apilot"
    title = page.locator("#main h1").first.bounding_box()
    assert row.bounding_box()["y"] > title["y"]  # under the title
    _shot(page, "header-" + path.split("/")[0], 1440)
    if path.startswith("skills/"):
        row.get_by_role("link", name="Harbour").click()
        page.wait_for_function("() => location.hash === '#r=projects%2Fharbour.md'")
        assert page.locator("#main h1").first.inner_text() == "Harbour"
    else:
        pilot.click()
        page.wait_for_function("() => location.hash.startsWith('#q=tag')")


CHIP_STYLE = """el => { const s = getComputedStyle(el); return {
  line: s.textDecorationLine, bg: s.backgroundColor, border: s.borderTopWidth, radius: parseFloat(s.borderTopLeftRadius),
  weight: s.fontWeight, shadow: s.boxShadow, color: s.color, height: el.getBoundingClientRect().height,
  paper: getComputedStyle(document.body).backgroundColor,
  grey: (() => { const d = document.createElement("span"); d.style.color = "var(--grey)"; document.body.append(d);
                 const c = getComputedStyle(d).color; d.remove(); return c; })() }; }"""


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("path", ["people/mara-ostrowski.md", "orgs/fernhill-labs.md", "projects/harbour.md",
                                  "skills/catalog/weekly-brief.md", "decisions/one-vocabulary.md"])
def test_a_tag_looks_like_a_tag_on_every_page_kind(reader, path, theme):
    """Owner, 2026-11-22: «那个标签为什么看起来不像标签？它是一个下划线的» (#3308). A tag is a quiet chip on every kind:
    a tint of its own, rounded, regular weight, no underline and no shadow, in light and dark, and it still opens
    the page it names. Every kind draws it through one component (tagLinks), so knowledge pages get the same."""
    open_page, _ = reader
    page = open_page("r=" + path.replace("/", "%2F"))
    page.evaluate("theme => document.documentElement.setAttribute('data-theme', theme)", theme)
    chip = page.locator("#main .page-tags a.tag-link").first
    chip.wait_for()
    style = chip.evaluate(CHIP_STYLE)
    assert style["line"] == "none", style  # not an underlined word any more
    assert style["bg"] not in ("rgba(0, 0, 0, 0)", "transparent", style["paper"]), style  # a tint of its own
    assert style["border"] == "1px", style  # a hairline edge
    assert style["color"] == style["grey"], style  # second ink, quieter than any action (#3313 review)
    assert style["radius"] > 0 and style["weight"] == "400" and style["shadow"] == "none", style
    assert 20 <= style["height"] <= 28, style  # a label's height, not the 40 px of 调查
    for width in (1440, 390):
        page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
        _shot(page, f"chip-{path.split('/')[0]}-{theme}", width)
    page.set_viewport_size({"width": 1440, "height": 900})
    chip.click()
    page.wait_for_function("() => location.hash.startsWith('#q=tag') || location.hash.startsWith('#r=')")
