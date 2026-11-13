"""Record pages lead with what the owner opens them for, in his words (sprint 15).

Seen on the owner's real copy: a 原文 chip above every untranslated name, the owner ranked among
"most connected" on All records, a person's open topics buried at the bottom, a jargon caption on
Skills, the phone avatar sitting in the action row, and an org's "N things in Today" larger than
Today's own count. Entity pages are records (D-30); a translation that has not arrived shows the
original quietly (D-103). The notebook is the invented one in tests/fixtures/rem_reader_notebook.py.
"""

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
MARA = "people/mara-ostrowski.md"
# Where the old chip sat: a person's hero, an org's crumb and title block, a project's eyebrow and title.
# A related page's snippet keeps its own small mark further down; that is not the page's language.
HEADERS = "#main :is(.person-head, .ov-over, .ov-say, .eyebrow, .page-head)"
MORE_TOPICS = """
- You owe Mara the revised seat price for the renewal; she asked on Monday.
- You owe Mara a date for the second training session.
- You owe Mara the invoice correction for September.
"""


def _notebook(root, now):
    from rem_reader_notebook import build
    from connectonion.rem.files import Notebook
    build(root, now)
    book = Notebook(root)
    # Five open topics, so the page shows its top three and says how many there are.
    text = book.read(MARA)
    head, _, rest = text.partition("## Open threads\n")
    topics, _, tail = rest.partition("\n## ")
    book.write(MARA, head + "## Open threads\n" + topics.rstrip("\n") + MORE_TOPICS + "\n## " + tail)
    # The owner's own page links to everyone, as it does on a real notebook: he is every page's hub.
    owner = book.read("people/avery-lin.md").replace("## Sources", "## People\n- [Mara Ostrowski](mara-ostrowski.md)\n"
                                                    "- [Tomás Reyes](tomas-reyes.md)\n- [Inès Halvorsen](ines-halvorsen.md)\n"
                                                    "- [Quinn Alder](quinn-alder.md)\n- [Noor Bakhtiar](noor-bakhtiar.md)\n"
                                                    "- [Harbour](../projects/harbour.md)\n- [Fernhill Labs](../orgs/fernhill-labs.md)\n\n## Sources")
    book.write("people/avery-lin.md", owner)
    return root


@pytest.fixture
def reader(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright
    from connectonion.rem import reader as rem_reader
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    frozen = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    html = rem_reader.render(_notebook(tmp_path / "rem", frozen), local=True)
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

        def open_page(hash_, width=1440, language="zh", live=False):
            page.set_viewport_size({"width": width, "height": 900})
            page.evaluate("""([hash, language, live]) => { REM.live = live; setInterfaceLanguage(language);
              location.hash = hash; render(); }""", [hash_, language, live], isolated_context=False)
            page.locator("#main h1").first.wait_for()
            return page

        yield open_page, calls
        browser.close()
    assert not errors, errors


def _box(locator):
    return locator.first.bounding_box()


# 1. 原文 was jargon in a chip above the name. A page simply in English with nothing requested says nothing.
@pytest.mark.parametrize("hash_", ["r=" + MARA.replace("/", "%2F"), "r=orgs%2Ffernhill-labs.md", "r=projects%2Fharbour.md"])
def test_an_english_page_with_no_translation_asked_for_carries_no_original_label(reader, hash_):
    open_page, _ = reader
    page = open_page(hash_)
    assert page.evaluate("!REM.status?.translation_coverage?.zh?.requested", isolated_context=False)
    for header in page.locator(HEADERS).all():
        assert "原文" not in header.inner_text()
    assert page.locator(HEADERS).locator(".lang-status").count() == 0
    assert page.locator("#main .translation-line").count() == 0


# A translation genuinely on its way is one quiet worded line by the body, never a chip above the name.
@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("hash_, head", [("r=" + MARA.replace("/", "%2F"), ".person-head"), ("r=orgs%2Ffernhill-labs.md", ".ov-say h1"),
                                         ("r=projects%2Fharbour.md", ".page-head")])
def test_a_pending_translation_is_one_quiet_line_below_the_header(reader, width, hash_, head):
    open_page, calls = reader
    page = open_page(hash_, width=width, live=True)
    line = page.locator("#main .translation-line")
    assert line.count() == 1
    assert line.inner_text() == "中文版还没好，先看原文"
    assert page.locator(HEADERS).locator(".lang-status").count() == 0
    assert _box(line)["y"] >= _box(page.locator(head))["y"] + _box(page.locator(head))["height"] - 1
    assert line.evaluate("n => getComputedStyle(n).fontSize") == page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--s-meta').trim()", isolated_context=False)
    assert any(path == "/rem/translation-request" for path, _ in calls)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


# 2. The owner is everyone's hub by definition; ranking him among "most connected" says nothing.
def test_most_connected_leaves_the_owner_out(reader):
    open_page, _ = reader
    page = open_page("c=all", language="en")
    page.locator(".gx-panel").wait_for()
    owner = page.evaluate("byPath(REM.owner).title", isolated_context=False)
    degree = page.evaluate("graphDegree(GRAPH.byId.get(GRAPH.nodes.find(n => n.r?.path === REM.owner).id))", isolated_context=False)
    assert degree >= 7  # he would lead the list
    hubs = page.locator(".gx-panel-body h3", has_text="Most connected").locator("xpath=following-sibling::*").all_inner_texts()
    assert hubs and not any(owner in hub for hub in hubs), hubs


# 3. Open topics are what he opens a person for: right under the header, top three, "全部 N 条".
@pytest.mark.parametrize("width", [1440, 390])
def test_open_topics_lead_the_person_page_with_the_top_three(reader, width):
    open_page, _ = reader
    page = open_page("r=" + MARA.replace("/", "%2F"), width=width)
    topics = page.locator(".r4-person .r4-topics")
    hero, first_widget = _box(page.locator(".person-head")), _box(page.locator(".r4-person .bento > *"))
    assert hero["y"] + hero["height"] <= _box(topics)["y"] < first_widget["y"]
    assert topics.locator("li").evaluate_all("rows => rows.filter(r => r.offsetParent).length") == 3
    more = topics.get_by_role("button")
    assert more.inner_text() == "全部 5 条"
    more.click()
    assert topics.locator("li").evaluate_all("rows => rows.filter(r => r.offsetParent).length") == 5
    # Still a record (D-30): nothing to mark, reply or close here.
    assert topics.locator("a, .chip:not(button)").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


# 4. The Skills page says what its numbers are on the cards, not in a caption about name matching.
def test_skills_has_no_matching_jargon(reader):
    open_page, _ = reader
    page = open_page("c=skills")
    page.locator(".skill-card").first.wait_for()
    text = page.locator("#main").inner_text()
    assert "按技能名称匹配计数" not in text and "匹配" not in text
    assert "近 180 天" in page.locator(".skill-card").first.inner_text()


# 5. On a phone the face belongs to the header beside the name, not in the row of contact buttons.
def test_phone_person_face_sits_with_the_name_not_the_actions(reader):
    open_page, _ = reader
    page = open_page("r=" + MARA.replace("/", "%2F"), width=390)
    face, name = _box(page.locator(".person-head .face")), _box(page.locator(".person-head h1"))
    acts = _box(page.locator(".person-head .hero-acts"))
    assert face["y"] < name["y"] + name["height"] and face["y"] + face["height"] > name["y"]  # same row as the name
    assert face["y"] + face["height"] <= acts["y"]  # above the contact row, not inside it
    assert face["x"] + face["width"] <= name["x"]


# 6. The org's link counts what Today counts: items waiting on you, never more than Today's own number.
def test_org_today_link_counts_what_today_counts(reader):
    open_page, _ = reader
    page = open_page("r=orgs%2Ffernhill-labs.md", language="en")
    assert page.locator(".ov-today").inner_text() == "5 things in Today involve Fernhill Labs →"
    # A promise gone stale is asked about apart and leaves Today's count; it must leave the org's too.
    page.evaluate("""() => {
      const org = byPath('orgs/fernhill-labs.md'), row = org.obligations.find(row => row.dir === 'mine' && !row.quiet);
      const old = '2026-03-01';
      for (const r of [row, ...REM.today_queue.filter(q => q.key === row.key)]) { r.due = old; r.since = old; }
      threadEntries.cached = null; render();
    }""", isolated_context=False)
    assert page.locator(".ov-today").inner_text() == "4 things in Today involve Fernhill Labs →"


# Review: with labelled passages hidden, the card counts and slices only what is shown, and leaves when nothing is.
@pytest.mark.parametrize("private_rows, expected", [(3, "还没结的话题\n2"), (5, None)])
def test_open_topics_count_only_shown_rows_when_labelled_passages_are_hidden(reader, private_rows, expected):
    open_page, _ = reader
    page = open_page("r=" + MARA.replace("/", "%2F"))
    page.evaluate("""n => {
      const r = byPath('people/mara-ostrowski.md');
      const rows = ['the signed addendum', 'the usage export', 'the seat price', 'a training date', 'the invoice correction']
        .map((what, i) => '- You owe Mara ' + what + (i >= 5 - n ? ' [personal]' : '') + '.');
      r.text = r.text.replace(/## Open threads\\n[\\s\\S]*?(?=\\n## )/, '## Open threads\\n' + rows.join('\\n') + '\\n');
      KNOWN.clear(); FACTS.clear();
      if (!document.documentElement.classList.contains('hide-private')) togglePrivate();
      render();
    }""", private_rows, isolated_context=False)
    topics = page.locator(".r4-person .r4-topics")
    if expected is None:
        assert topics.count() == 0 or not topics.is_visible()
    else:
        assert topics.inner_text().startswith(expected + "\n")
        assert "全部" not in topics.inner_text() and "[personal]" not in topics.inner_text()
    assert "5" not in page.locator(".r4-person .r4-topics h2, .r4-person .r4-topics .end").all_inner_texts().__str__()
