"""A course or team page titled by its code alone says what it is, everywhere an organisation's name shows.

The rc18 hunt (2026-11-23): "3900", "9900" and "3900/9900" headed the knowledge graph and the org tree as organisation
names. #3373 made such codes readable only in People's filter chips. A course page titled "1234" reads "课程 1234", a
team "团队 1234-T1A-PEAR", on the org page heading, its breadcrumb, the org tree, the Organisations list, the graph,
a person's organisation link and the tag chips. The notebook is the invented one in tests/fixtures/rem_reader_notebook.py.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
SHOTS = Path(os.environ.get("REM_PR_SHOTS", "/tmp/rem-course-orgs-shots"))
UNI, COURSE, PAIR, TEAM = ("orgs/example-edu-1a2b3c4d.md", "orgs/1234-c0ffee1234.md", "orgs/1234-5678-c0ffee5678.md",
                           "orgs/1234-t1a-pear-c0ffeeaaaa.md")
SOURCES = "\n## Sources\n- [1] gmail:fixture:9 — 2026-09-01\n- [2] gmail:fixture:9 — 2026-09-01\n"


def _unit(code, kind, parent):
    return (f"# {code}\n\n## Domains\n- Unknown\n\n## Facts\n- Kind: {kind} [1]\n- Parent: [[{parent}]] [2]\n"
            "- What they do: Unknown\n\n## Who they are\n- Unknown — not investigated yet\n" + SOURCES)


def _notebook(root, now):
    from rem_reader_notebook import build
    from connectonion.rem.files import Notebook
    build(root, now)
    book = Notebook(root)
    book.write(UNI, "# Example University\n\n## Domains\n- example.edu\n\n## Facts\n- Kind: university [1]\n" + SOURCES)
    book.write(COURSE, _unit("1234", "course", UNI))
    book.write(PAIR, _unit("1234/5678", "course", UNI))
    book.write(TEAM, _unit("1234-T1A-PEAR", "team", COURSE))
    mara = book.read("people/mara-ostrowski.md")
    book.write("people/mara-ostrowski.md", mara.replace("\n## Facts\n", f"\n## Facts\n- Unit: [[{TEAM}]] [1]\n", 1))
    return root


@pytest.fixture
def reader(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    html = rem_reader.render(_notebook(tmp_path / "rem", datetime(2026, 10, 1, 12, tzinfo=timezone.utc)), local=True)
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
        page.locator(".night-card .count, #main h1").first.wait_for()

        def go(where, width=1440):
            page.set_viewport_size({"width": width, "height": 900 if width > 400 else 844})
            page.evaluate("""([where]) => { setInterfaceLanguage("zh");
                location.hash = where.startsWith("orgs/") || where.startsWith("people/") ? href(byPath(where)).slice(1) : where;
                render(); }""", [where], isolated_context=False)
            page.locator("#main h1, #main .gx-list, #main table").first.wait_for()
            return page

        yield go
        browser.close()
    assert not errors, errors


def _shot(page, name, width):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}-{width}.png"), full_page=False)


def _bare(texts):
    """Texts that are a bare code: what the owner saw as an organisation's name."""
    return [text for text in texts if (text or "").strip() in ("1234", "1234/5678", "1234-T1A-PEAR")]


@pytest.mark.parametrize("width", [1440, 390])
def test_the_org_tree_and_heading_name_a_course_by_what_it_is(reader, width):
    page = reader(UNI, width)
    tree = page.locator("#main .ov-org-tree")
    tree.wait_for()
    labels = tree.locator("[role=treeitem]").all_inner_texts()
    words = [line for text in labels for line in text.splitlines()]
    assert not _bare(words), words
    assert any("课程 1234" == line.strip() for line in words), words
    # The page's other links (关联, relation cards) name the course too.
    links = page.locator("#main .ov-connections a, #main .relation-card strong").all_inner_texts()
    assert not _bare(links), links
    _shot(page, "org-tree", width)
    page = reader(TEAM, width)
    assert page.locator("#main h1.ov-name").inner_text().strip() == "团队 1234-T1A-PEAR"
    crumb = page.locator("#main .ov-crumb").inner_text()
    assert "课程 1234" in crumb and "Example University" in crumb, crumb


def test_the_organisations_list_and_a_persons_org_link_say_what_a_code_is(reader):
    page = reader("#c=orgs")
    cells = page.locator("#main table a, #main .org-tree a, #main li a").all_inner_texts()
    assert not _bare(cells), cells
    assert any("课程 1234/5678" in text for text in cells), cells
    person = reader("people/mara-ostrowski.md")
    bare = person.evaluate("""() => [...document.querySelectorAll("#main a[href*='1234']")]
        .filter(a => (a.textContent || "").trim() === "1234-T1A-PEAR")
        .map(a => a.outerHTML.slice(0, 240) + " @ " + (a.parentElement?.className || a.parentElement?.tagName))""",
                         isolated_context=False)
    assert not bare, bare


@pytest.mark.parametrize("width", [1440, 390])
def test_the_knowledge_graph_names_a_course_by_what_it_is(reader, width):
    page = reader("#view=graph", width)
    titles = page.evaluate("""() => GRAPH.nodes.filter(n => n.r && n.r.path.startsWith("orgs/")).map(graphTitle)""",
                           isolated_context=False)
    assert titles and not _bare(titles), titles
    assert "课程 1234" in titles and "团队 1234-T1A-PEAR" in titles, titles
    _shot(page, "graph", width)
