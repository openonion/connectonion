"""The relationships widget on a record page in a real browser (opt in with CO_REM_BROWSER_TEST=1).

An invented notebook. Ida Voss works at Tern Yard, where Sol Marek also works. Two coding sessions on
the Depot project ask Ida for something, so she reaches that project only through them. One sentence
on her page, about Wick Court, is labelled personal, so it draws no line. Max Hale links to seven organisations. Tide tables
is a knowledge entry nothing links to yet.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)

IDA = "#r=people%2Fida-voss.md"
ORGS = ["Ash Row", "Birch Lane", "Cedar Wharf", "Dune Street", "Elm Quay", "Fern Dock", "Gorse Pier"]


def notebook(root):
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    prepare(root)
    nb = Notebook(root)
    nb.write("people/ida-voss.md", "# Ida Voss\n## Facts\n- Role: Site planner\n\n## Insight\n"
             "- Ida works at [Tern Yard](../orgs/tern-yard.md) on the depot plan. [1]\n"
             "- [personal] Ida is leaving for [Wick Court](../orgs/wick-court.md) in spring. [1]\n\n"
             "## Sources\n- [1] gmail:i1 — 2026-02-03 — Ida\n")
    nb.write("people/sol-marek.md", "# Sol Marek\n## Facts\n- Role: Yard manager\n")
    nb.write("orgs/tern-yard.md", "# Tern Yard\n## People\n- [Sol Marek](../people/sol-marek.md) runs the yard. [1]\n\n"
             "## Sources\n- [1] gmail:t1 — 2026-01-20 — Tern Yard\n")
    nb.write("orgs/wick-court.md", "# Wick Court\nA housing office.\n")
    nb.stub_project("projects/depot.md", "Depot", ["/work/depot"])
    for key, day, ask in (("drawings", "2026-02-10", "sign the depot drawings"), ("survey", "2026-02-12", "send the site survey")):
        nb.write(f"sessions/{key}.md", f"# Depot {key}\n\n## Facts\n- Date: {day}\n- Agent: Codex\n- Project: [Depot](../projects/depot.md)\n"
                 f"- Folder: /work/depot\n- Session: {key}\n- Turns: 1\n\n## Follow-ups\n- Ask [Ida Voss](../people/ida-voss.md) to {ask}.\n\n"
                 f"## What you typed\n### 09:12\n> Plan the depot.\n\n## Final reply\n> Planned.\n\n## Sources\n- codex:{key}:1\n")
    nb.stub_topic("knowledge/tide-tables.md", "Tide tables", ["Tide tables"])
    nb.write("people/max-hale.md", "# Max Hale\n## Insight\n" + "".join(
        f"- Max advises [{name}](../orgs/{name.lower().replace(' ', '-')}.md). [1]\n" for name in ORGS)
        + "\n## Sources\n- [1] gmail:m1 — 2026-01-05 — Max\n")
    for name in ORGS:
        nb.write(f"orgs/{name.lower().replace(' ', '-')}.md", f"# {name}\nA client.\n")
    return root


@pytest.fixture
def reader(tmp_path, monkeypatch):
    """open(route, **context) -> a page on that route; every page is checked for errors and network use."""
    from patchright.sync_api import sync_playwright
    from connectonion.rem.reader import render
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    path = tmp_path / "reader.html"
    path.write_text(render(notebook(tmp_path / "rem"), local=True), encoding="utf-8")
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        errors, requests = [], []

        def open(route, width=1440, **context):
            page = browser.new_context(viewport={"width": width, "height": 900}, locale="en-US", **context).new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append(request.url) if request.url.startswith("http") else None)
            page.route("http*://**/*", lambda route: route.abort())
            page.goto(path.as_uri() + route)
            page.locator(".gx-local").wait_for()
            page.locator(".gx-local").scroll_into_view_if_needed()
            return page

        yield open
        browser.close()
        assert not errors, errors
        assert not requests, requests


def mark(page, name):
    return page.locator(f'.gx-local-svg a[aria-label^="{name}."]')


def lit(page):
    return sorted(label.split(".")[0] for label in page.locator(".gx-local-svg a.on").evaluate_all("marks => marks.map(a => a.getAttribute('aria-label'))"))


def test_a_person_has_two_rings_and_one_with_many_links_keeps_to_one(reader):
    page = reader(IDA)
    assert page.locator(".gx-local-svg a.near").count() == 2
    assert page.locator(".gx-local-svg a.far").get_attribute("aria-label") == "Sol Marek. Person. Yard manager · Through Tern Yard"
    assert page.locator(".gx-local-foot > span").first.inner_text() == "2 directly linked · 1 more through them"
    # Nothing is lit and no card is up until a mark is pointed at; the outer ring keeps its names to itself.
    assert page.locator(".gx-local-svg.lit, .gx-local-card.on").count() == 0
    assert page.locator(".gx-local-svg a.far text").evaluate("text => getComputedStyle(text).opacity") == "0"
    assert page.locator(".gx-local button", has_text="ring").count() == 0  # no depth switch: Open in graph has one
    # Seven direct links are a ring of their own; an organisation's ring is its people.
    page.goto(page.url.split("#")[0] + "#r=people%2Fmax-hale.md")
    page.locator(".gx-local-svg a.near").nth(6).wait_for()
    assert page.locator(".gx-local-svg a.far").count() == 0
    assert page.locator(".gx-local-foot > span").first.inner_text() == "7 directly linked"
    page.goto(page.url.split("#")[0] + "#r=orgs%2Ftern-yard.md")
    page.locator(".gx-local-svg a.near").first.wait_for()
    assert page.locator(".gx-local-svg a.far").count() == 0


@pytest.mark.parametrize("width, theme", [(1440, "light"), (390, "dark")])
def test_pointing_at_a_mark_lights_what_it_touches_and_a_card_says_why(reader, width, theme):
    page = reader(IDA, width=width, color_scheme=theme)
    card, tall = page.locator(".gx-local-card"), page.locator(".gx-local").bounding_box()["height"]
    mark(page, "Tern Yard").hover()
    card.locator("strong").wait_for()
    # Tern Yard, the person reached through it and Ida stay; Depot steps back.
    assert lit(page) == ["Ida Voss", "Sol Marek", "Tern Yard"]
    faded = "() => [...document.querySelectorAll('.gx-local-svg a:not(.on)')].every(mark => getComputedStyle(mark).opacity < .2)"
    page.wait_for_function(faded)
    assert page.locator(".gx-local-svg a:not(.on)").count() == 1
    page.wait_for_function("() => getComputedStyle(document.querySelector('.gx-local-svg a.far text')).opacity === '1'")
    # The card is Related pages' own entry: the kind and who linked, the name, the sentence, its citation.
    assert card.locator(".relation-kind").inner_text().startswith("Organisation · Linked from this page")
    assert card.locator("strong").inner_text() == "Tern Yard"
    assert card.locator(".relation-basis").inner_text() == "Ida works at Tern Yard on the depot plan."
    assert card.locator(".relation-provenance .cite").count() == 1
    # It floats: the widget keeps its height, the card stays on screen and off the marks it explains.
    assert page.locator(".gx-local").bounding_box()["height"] == tall
    box = card.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    for name in ("Tern Yard", "Sol Marek"):
        hit = mark(page, name).locator(".hit").bounding_box()
        assert hit["y"] + hit["height"] <= box["y"] or hit["y"] >= box["y"] + box["height"]
    # The pointer can travel to the card and use it.
    card.hover()
    page.wait_for_timeout(300)
    assert card.evaluate("card => card.classList.contains('on')")
    # The record in the middle lights its own ring and has no card: the page is already about it.
    page.locator(".gx-local-svg a.centre").hover()
    page.locator(".gx-local-card:not(.on)").wait_for(state="attached")
    assert lit(page) == ["Depot", "Ida Voss", "Tern Yard"]
    page.mouse.move(2, 2)
    page.locator(".gx-local-svg:not(.lit)").wait_for()
    # The keyboard does what the pointer does.
    mark(page, "Tern Yard").focus()
    card.locator("strong").wait_for()
    assert lit(page) == ["Ida Voss", "Sol Marek", "Tern Yard"]
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_a_project_reached_only_through_sessions_says_how_many(reader):
    page = reader(IDA)
    mark(page, "Depot").hover()
    card = page.locator(".gx-local-card")
    card.locator("strong").wait_for()
    # Ida's own page says "the depot plan", a name match and nothing more: the line is drawn by the two sessions.
    assert card.locator(".relation-kind").inner_text().startswith("Project · Through 2 sessions")
    assert card.locator(".relation-basis").inner_text().startswith("Ask Ida Voss to s")
    assert card.locator(".relation-provenance a").first.get_attribute("href").startswith("#r=sessions%2F")
    assert lit(page) == ["Depot", "Ida Voss"]


def test_a_mark_in_the_outer_ring_names_what_it_is_reached_through(reader):
    page = reader(IDA)
    mark(page, "Sol Marek").hover()
    card = page.locator(".gx-local-card")
    card.locator("strong").wait_for()
    assert card.locator("strong").inner_text() == "Sol Marek"
    assert card.locator(".relation-basis").inner_text() == "Yard manager · Through Tern Yard"
    assert lit(page) == ["Sol Marek", "Tern Yard"]  # not Ida: the two are not linked to each other


def test_a_finger_lights_a_mark_first_and_opens_it_second(reader):
    page = reader(IDA, width=390, has_touch=True)
    mark(page, "Tern Yard").tap()
    page.locator(".gx-local-card.on strong").wait_for()
    assert page.url.endswith(IDA) and lit(page) == ["Ida Voss", "Sol Marek", "Tern Yard"]
    mark(page, "Tern Yard").tap()
    page.wait_for_url("**#r=orgs%2Ftern-yard.md")


def test_a_link_inside_a_personal_passage_draws_no_line(reader):
    page = reader(IDA)
    # The sentence about Wick Court is labelled personal: it adds no mark, and no mark's words repeat it.
    assert mark(page, "Wick Court").count() == 0
    labels = page.locator(".gx-local-svg a").evaluate_all("marks => marks.map(a => a.getAttribute('aria-label') || '')")
    assert not any("leaving" in label for label in labels)


def test_all_relationships_opens_the_full_note_at_related_pages(reader):
    page = reader(IDA)
    assert not page.locator("details.deep-note").evaluate("fold => fold.open")
    page.locator(".gx-local-foot button", has_text="All relationships").click()
    assert page.locator("details.deep-note").evaluate("fold => fold.open")
    assert page.locator(".related-records h2").is_visible()
    assert page.locator(".gx-local-foot a").get_attribute("href") == "#view=graph&focus=people%2Fida-voss.md"


def test_a_record_nothing_links_to_says_so_and_draws_nothing(reader):
    page = reader("#r=knowledge%2Ftide-tables.md")
    assert page.locator(".gx-local h4").inner_text() == "Relationships"
    assert page.locator(".gx-local .gx-quiet-line").inner_text() == "Not in the graph yet"
    assert page.locator(".gx-local-svg, .gx-local-card, .gx-local-foot").count() == 0
