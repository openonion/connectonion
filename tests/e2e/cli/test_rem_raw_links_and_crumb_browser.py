"""The owner reads page names, never file paths, and a breadcrumb is a link only where its words are (#3318, #3319).

Seen on the owner's real notebook (rc7/rc8 hunt): a person page's relation card printed its basis as
"部门: [[orgs/<slug>.md]]", and the breadcrumb above a record title was a ~720 px wide link, so a click
on the blank strip beside the title jumped to the list. The notebook is the invented one in
tests/fixtures/rem_reader_notebook.py.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
MARA = "people/mara-ostrowski.md"
NOOR = "people/noor-bakhtiar.md"
PAGES = [MARA, NOOR, "orgs/fernhill-labs.md", "projects/harbour.md", "decisions/notebook-format.md",
         "skills/catalog/weekly-brief.md"]
# A stored id: a slug with a long hex tail, as record files are named on a real notebook.
HEX_ID = re.compile(r"-[0-9a-f]{10,}\b")


def _notebook(root, now):
    from rem_reader_notebook import build
    from connectonion.rem.files import Notebook
    build(root, now)
    book = Notebook(root)
    text = book.read(MARA)
    # A fact line naming her org the way stored text does, as a wiki link to a hex-named file and to a plain one.
    text = text.replace("- Company: [Fernhill Labs](../orgs/fernhill-labs.md) [2]",
                        "- Company: [Fernhill Labs](../orgs/fernhill-labs.md) [2]\n"
                        "- Department: [[orgs/fernhill-labs.md]] [2]\n"
                        "- Also seen at: [[orgs/old-studio-4c1d9e8f2a.md]] [2]", 1)
    book.write(MARA, text)
    # A page whose only link to Mara and to the org is a wiki link: that line becomes the relation card's basis.
    noor = book.read(NOOR)
    head, sep, rest = noor.partition("\n## ")
    book.write(NOOR, head.rstrip() + "\n- Introduced by: [[people/mara-ostrowski.md]] [1]\n"
               "- Department: [[orgs/fernhill-labs.md]] [1]\n\n" + sep.lstrip("\n") + rest)
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
        page.locator(".night-card .count").wait_for()

        def open_page(hash_, language="zh"):
            page.evaluate("""([hash, language]) => { setInterfaceLanguage(language); location.hash = hash; render(); }""",
                          [hash_, language], isolated_context=False)
            page.locator("#main h1").first.wait_for()
            return page

        yield open_page
        browser.close()
    assert not errors, errors


@pytest.mark.parametrize("record", PAGES)
@pytest.mark.parametrize("language", ["zh", "en"])
def test_no_page_shows_a_wiki_link_or_a_stored_id(reader, record, language):
    page = reader("#r=" + record.replace("/", "%2F"), language)
    text = page.locator("#main").inner_text()
    assert "[[" not in text and "]]" not in text, re.findall(r".{0,30}\[\[.{0,40}", text)
    assert not HEX_ID.search(text), HEX_ID.findall(text)


@pytest.mark.parametrize("record, named", [(NOOR, "Mara Ostrowski"), (MARA, "Mara Ostrowski")])
def test_a_relation_card_names_the_page_its_basis_links(reader, record, named):
    page = reader("#r=" + record.replace("/", "%2F"))
    bases = page.evaluate("() => [...document.querySelectorAll('#main .relation-basis')].map(e => e.textContent)",
                          isolated_context=False)
    joined = " | ".join(bases)
    assert any("Introduced by" in basis and named in basis for basis in bases), joined
    assert not any("[[" in basis or ".md" in basis for basis in bases), joined


def test_the_review_and_connection_cards_name_pages(reader):
    page = reader("#reviews=1")
    page.evaluate("""() => { REM.reviews = [{ id: "r1", kind: "link", status: "pending",
        subjects: ["orgs/fernhill-labs.md", "people/mara-ostrowski.md"],
        question: "Does [[people/mara-ostrowski.md]] concern people/quinn-alder.md?",
        basis: "Seen in [[orgs/fernhill-labs.md|the pilot org]] notes.", created_at: "2026-09-30T00:00:00+00:00" }];
        render(); }""", isolated_context=False)
    text = page.locator("#main").inner_text()
    assert "Mara Ostrowski" in text and "the pilot org" in text, text[:400]
    assert "[[" not in text and ".md" not in text, text[:400]
    # The same row on Today's connection card.
    page.evaluate("() => { location.hash = ''; render(); }", isolated_context=False)
    card = page.evaluate("() => document.querySelector('#main .connection-review')?.textContent || ''", isolated_context=False)
    assert "Mara Ostrowski" in card and "[[" not in card and ".md" not in card, card


@pytest.mark.parametrize("record", [MARA, "orgs/fernhill-labs.md", "skills/catalog/weekly-brief.md",
                                    "projects/harbour.md"])
def test_the_crumb_is_a_link_only_where_its_words_are(reader, record):
    page = reader("#r=" + record.replace("/", "%2F"))
    crumb = page.locator("#main :is(a.page-crumb, .ov-crumb a, a.gx-crumb, .eyebrow a)").first
    if not crumb.count():
        pytest.skip("this page kind renders no crumb link")
    box = crumb.bounding_box()
    words = page.evaluate("""el => { const r = document.createRange(); r.selectNodeContents(el);
        return r.getBoundingClientRect().width; }""", crumb.element_handle(), isolated_context=False)
    assert box["width"] <= words * 3 + 48, (box, words)  # a touch target may pad the words, never span the column
    before = page.evaluate("location.hash")
    # 100 px past the words, still inside the old full-width block.
    x, y = box["x"] + words + 100, box["y"] + box["height"] / 2
    page.mouse.click(x, y)
    assert page.evaluate("location.hash") == before
    page.mouse.click(box["x"] + 4, y)
    assert page.evaluate("location.hash") != before


def test_a_named_page_in_prose_is_an_ordinary_link_and_a_card_never_nests_one(reader):
    # Art director, #3338: a converted name in a passage looks like every other in-text link (no bold, no colour),
    # and inside a card that is already a link the name stays text.
    page = reader("#r=" + NOOR.replace("/", "%2F"), "en")
    page.evaluate("""() => { const p = document.createElement('p'); p.id = 'probe';
        p.innerHTML = inline('Works with [Fernhill Labs](../orgs/fernhill-labs.md) and [[people/mara-ostrowski.md]] [1].', 'people/noor-bakhtiar.md');
        document.querySelector('#main').appendChild(p); }""", isolated_context=False)
    styles = page.evaluate("""() => [...document.querySelectorAll('#probe a:not(.cite)')].map(a => { const s = getComputedStyle(a);
        return [a.textContent, s.fontWeight, s.color, s.textDecorationLine, s.textDecorationColor, s.textUnderlineOffset]; })""",
                           isolated_context=False)
    assert [row[0] for row in styles] == ["Fernhill Labs", "Mara Ostrowski"], styles
    assert styles[0][1:] == styles[1][1:], styles
    assert page.evaluate("() => document.querySelectorAll('#main a a').length", isolated_context=False) == 0
    assert page.evaluate("() => document.querySelectorAll('#main .relation-card a').length", isolated_context=False) == 0
