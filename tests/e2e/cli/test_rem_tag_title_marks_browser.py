"""A tag page's title never carries a privacy mark, and two masked pages never read as one (#3385).

Opt in with CO_REM_BROWSER_TEST=1. An invented notebook: two tag pages an older writer titled "X [personal]"
(a language and a habit), the people who carry those tags, and two private topics that are not tag pages.
At the default "cover" level the reader used to show every marked title as the same "Personal".
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)

TAG_PAGE = """# {title} [personal]

{title} is what Mara and Quinn share [1].

- Tags: {slug}

## Pages
- [Mara Ostrowski](../people/mara-ostrowski.md)
- [Quinn Alder](../people/quinn-alder.md)

Investigation: investigated 2026-11-20 (tag page, from 2 pages)

## Sources
- [1] gmail:m1
"""


def notebook(root):
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook, state_path, write_json
    prepare(root)
    nb = Notebook(root)
    # Written by an older release, before tag titles were refused and before masked pages were numbered:
    # straight to disk, as the owner's notebook holds them.
    (root / "knowledge").mkdir(exist_ok=True)
    for slug, title in (("python", "Python"), ("night-runs", "Night runs")):
        (root / "knowledge" / f"{slug}.md").write_text(TAG_PAGE.format(title=title, slug=slug), encoding="utf-8")
    for slug, name in (("mara-ostrowski", "Mara Ostrowski"), ("quinn-alder", "Quinn Alder")):
        nb.write(f"people/{slug}.md", f"# {name}\n\n## Facts\n- Tags: python [1], night-runs [1]\n\n## Insight\n"
                 f"- {name} writes Python and runs at night [1].\n- Linked to [Night notes](../knowledge/night-notes.md) "
                 f"and [Garden diary](../knowledge/garden-diary.md) [1].\n\n## Sources\n- [1] gmail:m1 — 2026-02-03\n")
    nb.write("knowledge/night-notes.md", "# Night notes [personal]\n\nA private topic [1].\n\n## Sources\n- [1] gmail:m1\n")
    nb.write("knowledge/garden-diary.md", "# Garden diary [personal]\n\nAnother private topic [1].\n\n## Sources\n- [1] gmail:m1\n")
    write_json(state_path(root, "tags.json"), {"tags": {
        "python": {"label": "Python", "kind": "topic", "aliases": [], "page": "knowledge/python.md"},
        "night-runs": {"label": "Night runs", "kind": "topic", "aliases": [], "page": "knowledge/night-runs.md"}}})
    return root


@pytest.fixture
def page(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem.reader import render
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = notebook(tmp_path / "rem")
    path = tmp_path / "reader.html"
    path.write_text(render(root, local=True), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="en-US")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("http*://**/*", lambda route: route.abort())
        page.goto(path.as_uri())
        yield page, path.as_uri(), root
        browser.close()
        assert not errors, errors


def test_the_page_build_unmarks_tag_titles_and_keeps_their_lines_private(page):
    _, _, root = page
    from connectonion.rem.files import Notebook
    text = Notebook(root).read("knowledge/python.md")
    assert text.splitlines()[0] == "# Python"
    assert "is what Mara and Quinn share [1]. [personal]" in text
    # A private topic that is not a tag page stays private as a whole.
    assert Notebook(root).read("knowledge/night-notes.md").startswith("# Night notes [personal]")


def test_tag_pages_keep_their_names_in_the_graph_and_on_a_person_page(page):
    page, uri, _ = page
    page.locator('#nav a[href="#c=knowledge"]').click()
    page.locator(".gx-map canvas").wait_for()
    titles = page.evaluate("() => graphModel().nodes.filter(n => n.k === 'knowledge').map(graphTitle).sort()", isolated_context=False)
    assert "Python" in titles and "Night runs" in titles
    page.goto(uri + "#r=people%2Fmara-ostrowski.md")
    links = page.locator(".tag-link")
    links.first.wait_for()
    assert set(links.all_inner_texts()) == {"Python", "Night runs"}
    assert page.locator('.tag-link:has-text("Python")').first.get_attribute("href") == "#r=knowledge%2Fpython.md"


def masked_labels(page):
    return page.evaluate("() => Object.fromEntries(graphModel().nodes.filter(graphHidden).map(n => [n.id, graphTitle(n)]))",
                         isolated_context=False)


def open_graph(page, url):
    page.goto(url)
    page.locator(".gx-map canvas").wait_for()


def rebuilt(root, tmp_path, name):
    from connectonion.rem.reader import render
    path = tmp_path / name
    path.write_text(render(root, local=True), encoding="utf-8")
    return path.as_uri() + "#c=knowledge"


def link_from_mara(root, record, name):
    from connectonion.rem.files import Notebook
    nb = Notebook(root)
    nb.write("people/mara-ostrowski.md", nb.read("people/mara-ostrowski.md").replace(
        "## Sources", f"- Also [{name}](../{record}) [1].\n\n## Sources"))


def test_masked_pages_read_personal_one_and_two_in_the_order_they_were_masked(page):
    page, uri, _ = page
    open_graph(page, uri + "#c=knowledge")
    # Night notes was written first, Garden diary second (masked.py numbers them where they are written).
    assert masked_labels(page) == {"knowledge/night-notes.md": "Personal 1", "knowledge/garden-diary.md": "Personal 2"}
    page.reload()
    page.locator(".gx-map canvas").wait_for()
    assert masked_labels(page) == {"knowledge/night-notes.md": "Personal 1", "knowledge/garden-diary.md": "Personal 2"}


def test_a_new_private_page_never_renumbers_the_others(page, tmp_path):
    """The art director's rule on #3386: 「个人事项 1」 never becomes 2. A number belongs to its page."""
    page, uri, root = page
    from connectonion.rem.files import Notebook
    open_graph(page, uri + "#c=knowledge")
    before = masked_labels(page)
    # A private page whose path sorts before both, linked so it draws: an ordinal would shift every label.
    Notebook(root).write("knowledge/aaa-early.md", "# Early [personal]\n\nA third private topic [1].\n\n## Sources\n- [1] gmail:m1\n")
    link_from_mara(root, "knowledge/aaa-early.md", "Early")
    open_graph(page, rebuilt(root, tmp_path, "reader-2.html"))
    after = masked_labels(page)
    assert {k: after[k] for k in before} == before
    assert after["knowledge/aaa-early.md"] == "Personal 3"


def test_a_deleted_pages_number_is_never_reused(page, tmp_path):
    page, uri, root = page
    from connectonion.rem.files import Notebook
    nb = Notebook(root)
    nb.delete("knowledge/garden-diary.md")  # Personal 2 is gone
    nb.write("knowledge/third.md", "# Third [personal]\n\nA new private topic [1].\n\n## Sources\n- [1] gmail:m1\n")
    link_from_mara(root, "knowledge/third.md", "Third")
    open_graph(page, rebuilt(root, tmp_path, "reader-3.html"))
    labels = masked_labels(page)
    assert labels["knowledge/night-notes.md"] == "Personal 1"
    assert labels["knowledge/third.md"] == "Personal 3"


def test_a_legacy_page_with_no_number_follows_the_highest_without_writing(page, tmp_path):
    page, uri, root = page
    # Written before numbering existed: straight to disk, no "Masked:" line.
    legacy = root / "knowledge" / "old-private.md"
    legacy.write_text("# Old private [personal]\n\nFrom an older release [1].\n\n## Sources\n- [1] gmail:m1\n", encoding="utf-8")
    link_from_mara(root, "knowledge/old-private.md", "Old private")
    before = legacy.read_text(encoding="utf-8")
    open_graph(page, rebuilt(root, tmp_path, "reader-4.html"))
    assert masked_labels(page)["knowledge/old-private.md"] == "Personal 3"
    assert legacy.read_text(encoding="utf-8") == before  # the reader only reads
