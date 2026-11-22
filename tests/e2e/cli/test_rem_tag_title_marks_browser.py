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
    for slug, title in (("python", "Python"), ("night-runs", "Night runs")):
        nb.write(f"knowledge/{slug}.md", TAG_PAGE.format(title=title, slug=slug))
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


def test_two_masked_pages_never_share_one_label(page):
    page, _, _ = page
    page.locator('#nav a[href="#c=knowledge"]').click()
    page.locator(".gx-map canvas").wait_for()
    masked = page.evaluate("() => graphModel().nodes.filter(graphHidden).map(graphTitle)", isolated_context=False)
    assert len(masked) == 2 and len(set(masked)) == 2, masked
    assert all(label.startswith("Personal") for label in masked)
    # The same numbers on the next build: a label is stable, not a shuffle.
    page.reload()
    page.locator(".gx-map canvas").wait_for()
    assert page.evaluate("() => graphModel().nodes.filter(graphHidden).map(graphTitle)", isolated_context=False) == masked


def masked_labels(page):
    return page.evaluate("() => Object.fromEntries(graphModel().nodes.filter(graphHidden).map(n => [n.id, graphTitle(n)]))",
                         isolated_context=False)


def test_a_new_private_page_never_renumbers_the_others(page, tmp_path):
    """The art director's rule on #3386: 「个人事项 1」 never becomes 2. A number belongs to its page."""
    page, uri, root = page
    from connectonion.rem.files import Notebook
    from connectonion.rem.reader import render
    page.locator('#nav a[href="#c=knowledge"]').click()
    page.locator(".gx-map canvas").wait_for()
    before = masked_labels(page)
    # A private page whose path sorts before both, linked so it draws: an ordinal would shift every label.
    nb = Notebook(root)
    nb.write("knowledge/aaa-early.md", "# Early [personal]\n\nA third private topic [1].\n\n## Sources\n- [1] gmail:m1\n")
    nb.write("people/mara-ostrowski.md", nb.read("people/mara-ostrowski.md").replace(
        "## Sources", "- Also [Early](../knowledge/aaa-early.md) [1].\n\n## Sources"))
    path = tmp_path / "reader-2.html"
    path.write_text(render(root, local=True), encoding="utf-8")
    page.goto(path.as_uri() + "#c=knowledge")
    page.locator(".gx-map canvas").wait_for()
    after = masked_labels(page)
    assert len(after) == 3 and len(set(after.values())) == 3, after
    assert {k: after[k] for k in before} == before
