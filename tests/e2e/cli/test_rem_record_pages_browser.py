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
    # A phone number and a GitHub handle, so her header carries all three contact buttons (owner, 2026-11-17).
    text = (head + "## Open threads\n" + topics.rstrip("\n") + MORE_TOPICS + "\n## " + tail).replace(
        "- Phone: Unknown", "- Phone: +64 21 555 0142 (mobile) [1]").replace("- Handles: mara@fernhill.example", "- Handles: mara-o (GitHub)")
    assert "mara-o (GitHub)" in text and "+64 21 555 0142" in text
    book.write(MARA, text)
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


# A translation genuinely on its way is said once, by the top bar's language control (#3143), never in the page.
@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("hash_, head", [("r=" + MARA.replace("/", "%2F"), ".person-head"), ("r=orgs%2Ffernhill-labs.md", ".ov-say h1"),
                                         ("r=projects%2Fharbour.md", ".page-head")])
def test_a_pending_translation_is_the_top_bars_one_language_control_not_a_line_in_the_page(reader, width, hash_, head):
    """#3143 (owner, 2026-11-19): the page's translate button and the EN/中 switch are one control, in one place."""
    open_page, calls = reader
    page = open_page(hash_, width=width, live=True)
    assert page.locator("#main .translation-line, #main .translate-all").count() == 0
    assert page.locator(HEADERS).locator(".lang-status").count() == 0
    progress = page.locator("#lang-progress")
    assert progress.is_visible() and "还没有中文版" in progress.inner_text()
    # Beside the EN/中 toggle in the top bar, in the 13px label size.
    toggle = _box(page.locator("#lang-toggle"))
    assert abs(_box(progress)["y"] + _box(progress)["height"] / 2 - (toggle["y"] + toggle["height"] / 2)) < 8
    assert progress.evaluate("n => getComputedStyle(n).fontSize") == page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--s-ui').trim()", isolated_context=False)
    assert any(path == "/rem/translation-request" for path, _ in calls)   # the opened page is still asked for at once
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


# 2. The owner is everyone's hub by definition; ranking him among "most connected" says nothing.
def test_most_connected_leaves_the_owner_out(reader):
    open_page, _ = reader
    page = open_page("view=graph", language="en")
    page.locator(".gx-panel").wait_for()
    owner = page.evaluate("byPath(REM.owner).title", isolated_context=False)
    degree = page.evaluate("graphDegree(GRAPH.byId.get(GRAPH.nodes.find(n => n.r?.path === REM.owner).id))", isolated_context=False)
    assert degree >= 7  # he would lead the list
    hubs = page.locator(".gx-panel-guide .gx-item").all_inner_texts()
    assert hubs and not any(owner in hub for hub in hubs), hubs


# 3. Open topics are what he opens a person for: right under the header, top three, "全部 N 条".
@pytest.mark.parametrize("width", [1440, 390])
def test_the_headers_today_count_drops_when_an_item_is_closed_in_today(reader, width):
    """#3145: what is open shows only as the header's count, from Today's own state; closed there, gone here."""
    open_page, _ = reader
    page = open_page("r=" + MARA.replace("/", "%2F"), width=width)
    count = lambda: page.evaluate("waitingOn(byPath('people/mara-ostrowski.md')).length", isolated_context=False)  # noqa: E731
    before = count()
    assert before >= 1
    page.evaluate("() => { const e = waitingOn(byPath('people/mara-ostrowski.md'))[0]; threadStates[doneKey(e)] = { state: 'done', at: new Date().toISOString() }; render(); }",
                  isolated_context=False)
    assert count() == before - 1
    link = page.locator(".person-head .hero-meta .r4-today")
    assert (link.count() == 0) if before == 1 else (str(before - 1) in link.inner_text())


# 4. The Skills page says what its numbers are in the column's header (#3094), not in a caption about name matching.
def test_skills_has_no_matching_jargon(reader):
    open_page, _ = reader
    page = open_page("c=skills")
    page.locator(".skill-table tbody tr").first.wait_for()
    text = page.locator("#main").inner_text()
    assert "按技能名称匹配计数" not in text and "匹配" not in text
    assert "近 180 天" in page.locator(".skill-table thead th.c-uses").inner_text()


# 5. On a phone the face belongs to the header beside the name, not in the row of contact buttons.
def test_phone_person_face_sits_with_the_name_not_the_actions(reader):
    open_page, _ = reader
    page = open_page("r=" + MARA.replace("/", "%2F"), width=390)
    face, name = _box(page.locator(".person-head .face")), _box(page.locator(".person-head h1"))
    acts = _box(page.locator(".person-head .hero-acts"))
    assert face["y"] < name["y"] + name["height"] and face["y"] + face["height"] > name["y"]  # same row as the name
    assert face["y"] + face["height"] <= acts["y"]  # above the contact row, not inside it
    assert face["x"] + face["width"] <= name["x"]


# 5b. The owner called the contact pictures "not very accurate": a phone number was a smartphone and a GitHub
# handle a speech bubble. Each is now the published picture, the same size as its neighbours, centred in its
# button, and its kind is said in words beside the value on hover and in its name.
@pytest.mark.parametrize("width", [1440, 390])
def test_contact_rows_say_their_kind_in_words_and_copy_on_a_click(reader, width):
    """The profile card's rows (#3131, owner 2026-11-19: «资料卡片很丑»): each says its kind in a word in one label
    column, with no picture beside some labels and not others, and an address, phone or handle copies on a click."""
    open_page, _ = reader
    page = open_page("r=" + MARA.replace("/", "%2F"), width=width, language="en")
    rows = page.locator(".person-head .pcard .pc-row").evaluate_all("""rows => rows.map(r => ({
      word: r.querySelector('.pc-k').textContent, picture: !!r.querySelector('.pc-k svg'), copy: !!r.querySelector('.pc-copy')}))""")
    assert [r["word"] for r in rows][:3] == ["Email", "Phone", "GitHub"]
    assert all(r["copy"] for r in rows[:3])
    assert not any(r["picture"] for r in rows)  # one label language: words
    assert page.locator(".person-head .round").count() == 0


# 6. Organisation records never project Today's queue, even when obligations change.
def test_org_record_has_no_today_projection(reader):
    open_page, _ = reader
    page = open_page("r=orgs%2Ffernhill-labs.md", language="en")
    assert page.locator(".ov-today").count() == 0
    assert "Today" not in page.locator("#main").inner_text()
    page.evaluate("""() => {
      for (const r of REM.records) if (r.category === 'orgs') r.obligations = [];
      threadEntries.cached = null; render();
    }""", isolated_context=False)
    assert page.locator(".ov-today").count() == 0
    assert page.locator(".ov-org-tree [role=tree]").is_visible()


# 7. The profile card is the first thing on the person page (owner, 2026-11-18): every known fact under the name,
# nothing to expand, each fact in one place. #3131 (2026-11-19): one line per fact, place and last contact in the
# header's third line, and what is unknown in the card's tooltip, not a line of "not found".
@pytest.mark.parametrize("width", [1440, 390])
def test_profile_card_shows_every_known_fact_under_the_name_without_expanding(reader, width):
    open_page, _ = reader
    page = open_page("r=" + MARA.replace("/", "%2F"), width=width, language="en")
    page.evaluate("""() => {
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace(/^- Phone:[^\\n]*/m, '- Phone: +64 21 555 0199 (mobile) [2]')
        .replace(/^- Signing entity:[^\\n]*/m, '- Signing entity: Fernhill Labs Ltd [2]')
        .replace(/^- Handles:[^\\n]*/m, '- Handles: mara@fernhill.example; github.com/mara-o (GitHub) [2]; mara#2041 (Discord) [3]');
      // rem.test is not a secure origin, so the page has no clipboard of its own here.
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: text => { window.copied = text; return Promise.resolve(); } } });
      delete r.original; delete r.translations; KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    card = page.locator(".person-head .pcard")
    # The card is in the header, outside Full memory: it shows whether or not Full memory is open (#3104 opens it).
    assert card.is_visible() and card.evaluate("n => !n.closest('details')")
    name, box = _box(page.locator(".person-head h1")), _box(card)
    assert name["y"] + name["height"] <= box["y"] < 844, "the card is under the name, on the first screen"
    labels = card.locator(".pc-k").all_inner_texts()
    for label in ["Email", "Phone", "GitHub", "Discord", "Signing entity", "How we know them", "First contact",
                  "Also known as", "Language"]:
        assert label in labels, label
    meta = page.locator(".person-head .hero-meta").inner_text()
    assert "Last contact" in meta and "Last contact" not in labels and "Location" not in labels  # said once, in the header
    text = card.inner_text()
    assert "+64 21 555 0199" in text and "Fernhill Labs Ltd" in text and "M. Ostrowski" in text
    assert "not found" not in text and "Time zone" not in labels  # no rows or lines of "not found"
    assert "1 fact not found" in card.get_attribute("title")  # what is unknown is one hover away
    # Every fact is one row: a label column beside its value, never a label stacked over it.
    for row in card.locator(".pc-row").all()[:4]:
        k, v = _box(row.locator(".pc-k")), _box(row.locator(".pc-v"))
        assert abs(k["y"] - v["y"]) < 6 and k["x"] + k["width"] <= v["x"]
    # One place per fact: role and organisation are the line under the name, not chips, rows or round buttons.
    assert "Head of Partnerships" in page.locator(".r4-sub").inner_text() and "Head of Partnerships" not in text
    assert page.locator(".person-head .round, .r4-sub .chip").count() == 0
    assert labels.count("Email") == 1 and text.count("mara@fernhill.example") == 1  # the handle that is an email is not repeated
    phone = card.locator(".pc-row", has=page.locator(".pc-k", has_text="Phone")).locator("button")
    phone.click()
    assert "Copied" in phone.inner_text() and page.evaluate("window.copied", isolated_context=False) == "+64 21 555 0199"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_the_header_meta_line_keeps_a_gap_and_a_dot_between_every_item(reader, width):
    """Mac review of rc28: '43 封邮●今天 · 逾期 16 天' and '36 封邮件今天里有 6 件': the Today link lost its gap and dot."""
    open_page, _ = reader
    page = open_page("r=" + MARA.replace("/", "%2F"), width=width)
    page.evaluate("""() => { const meta = document.querySelector('.person-head .hero-meta');
      const late = Object.assign(document.createElement('a'), { className: 'r4-today late', href: '#', textContent: '今天 · 逾期 16 天' });
      meta.append(Object.assign(document.createElement('span'), { textContent: '43 封邮件' }), late); }""", isolated_context=False)
    gaps = page.evaluate("""() => { const items = [...document.querySelectorAll('.person-head .hero-meta > *')], out = [];
      for (let i = 1; i < items.length; i++) { const a = items[i - 1].getBoundingClientRect(), b = items[i].getBoundingClientRect();
        if (Math.abs(a.top - b.top) < 4) out.push(Math.round(b.left - a.right)); }
      return out; }""", isolated_context=False)
    assert gaps and all(gap >= 12 for gap in gaps), gaps
    dot = page.locator(".person-head .hero-meta .r4-today.late").evaluate("n => getComputedStyle(n, '::before').content")
    assert dot == '"·"', dot


@pytest.mark.parametrize("width", [1440, 390])
def test_a_person_page_leads_with_what_happened_and_a_row_opens_its_original(reader, width):
    """#3145 (owner, 2026-11-19): no 还没结的话题 (it disagreed with Today); 往来 is first under the header, newest first,
    and one click on a row shows its whole original beside it, the row marked while it is open."""
    open_page, _ = reader
    page = open_page("r=" + MARA.replace("/", "%2F"), width=width)
    assert page.locator(".r4-person .r4-topics").count() == 0
    timeline = page.locator(".r4-person > .tl-lead")
    head = page.locator(".person-head").bounding_box()
    assert timeline.bounding_box()["y"] >= head["y"] + head["height"] - 1
    assert page.evaluate("document.querySelector('.r4-person > .tl-lead').previousElementSibling.classList.contains('person-head')")
    days = timeline.locator(".tl-e .d").all_inner_texts()
    assert days, "the timeline shows rows"
    assert timeline.locator(".tl-e.tl-open").count(), timeline.locator(".tl-e").first.evaluate("n => n.outerHTML.slice(0, 600)")
    row = timeline.locator(".tl-e.tl-open").first
    row.click()
    panel = page.locator("#evidence-panel")
    panel.wait_for(state="visible")
    assert panel.locator(".evidence-claim").count() == 0 and "null" not in panel.inner_text()
    assert "on" in row.get_attribute("class")
    if os.environ.get("REM_PR_SHOTS"):
        page.screenshot(path=os.path.join(os.environ["REM_PR_SHOTS"], f"person-timeline-open-{width}.png"))
    page.keyboard.press("Escape")
    assert not panel.is_visible() and "on" not in (row.get_attribute("class") or "").split()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_people_never_show_an_address_as_a_name_and_cells_never_overlap(reader, width):
    """#3157: rows named by an address, organisation cells carrying provenance prose, long names drawn over the next
    column. An address-titled page reads as 'name unknown' with its address quiet; provenance is a tooltip."""
    open_page, _ = reader
    page = open_page("c=people", width=width, language="zh")
    page.evaluate("""() => {
      const r = byPath('people/mara-ostrowski.md');
      REM.records.push({...r, path: 'people/someone-at-example.md', title: 'someone.unknown@example.test',
        text: '# someone.unknown@example.test\\n\\n## Facts\\n- Email: someone.unknown@example.test\\n- Company: Fernhill Labs (their signature)\\n'});
      REM.records.push({...r, path: 'people/long-name.md', title: 'Maximiliana Theodora Wolfeschlegelsteinhausen-Bergerdorff',
        text: '# Maximiliana Theodora Wolfeschlegelsteinhausen-Bergerdorff\\n\\n## Facts\\n- Company: Fernhill Labs\\n'});
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    rows = page.locator(".people-table tbody tr")
    text = page.locator(".people-table tbody").inner_text()
    assert "someone.unknown@example.test" not in page.locator(".people-table td.c-name a").all_inner_texts()
    assert "未知姓名" in text
    assert "(their signature)" not in text  # provenance moves to the tooltip
    if width == 1440:
        overlap = page.evaluate("""() => [...document.querySelectorAll('.people-table tbody tr')].some(tr => {
          const name = tr.querySelector('td.c-name'), org = tr.querySelector('td.c-org');
          if (!name || !org) return false;
          const inner = name.querySelector('a').getBoundingClientRect(), cell = name.getBoundingClientRect();
          return inner.right > cell.right + 1; })""", isolated_context=False)
        assert not overlap
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_orgs_merge_same_named_units_keep_people_out_and_hide_empty_columns(reader):
    """#3160: a unit listed twice, a person's role filed as an organisation, columns mostly '—', and '推断' as a line."""
    open_page, _ = reader
    page = open_page("c=orgs", width=1440, language="zh")
    page.evaluate("""() => {
      const base = byPath('orgs/fernhill-labs.md');
      const org = (path, title, extra = {}) => ({...base, path, title, text: '# ' + title + '\\n\\n## Facts\\n- Kind: company\\n', children: [], parent: undefined, unit_kind: undefined, people: [], ...extra});
      REM.records.push(org('orgs/eng-a.md', 'Faculty of Engineering', {unit_kind: 'faculty'}), org('orgs/eng-b.md', 'Faculty of Engineering', {unit_kind: 'faculty'}),
        org('orgs/deputy.md', 'Deputy Director, Research Partnerships'));
      for (let i = 0; i < 6; i++) REM.records.push(org('orgs/filler-' + i + '.md', 'Filler Company ' + i));
      KNOWN.clear(); FACTS.clear(); orgTableColumns = null; render();
    }""", isolated_context=False)
    names = page.locator(".org-table tbody td.c-name a").all_inner_texts()
    assert names.count("Faculty of Engineering") == 1
    assert not any("Deputy Director" in n for n in names)
    headers = page.locator(".org-table thead th").all_inner_texts()
    assert not any("位置" in h for h in headers)  # empty for 80%+ of rows
    assert page.locator(".org-table .org-site small").count() == 0  # 推断 is a dot with a tooltip, not a line
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_decision_titles_carry_no_privacy_label_and_leads_no_timestamps(reader):
    """#3159: a title ended with a literal '[personal]'; leads opened with '这项选择作于 2026-11-08 的 10:20…'."""
    open_page, _ = reader
    page = open_page("c=decisions", width=1440, language="zh")
    page.evaluate("""() => {
      REM.records.push({path: 'decisions/keep-markdown.md', title: 'Keep Markdown [personal]', category: 'decisions', written: true,
        text: '# Keep Markdown [personal]\\n\\n## Decision\\n这项选择作于 2026-11-08 的 10:20，所在会话开始于 2026-10-29T09:00:00Z。保留 Markdown 作为笔记格式。 [1]\\n\\n## Sources\\n- [1] codex:01a1a594\\n'});
      KNOWN.clear(); FACTS.clear(); render();
    }""", isolated_context=False)
    text = page.locator("#main").inner_text()
    assert "[personal]" not in text and "Keep Markdown" in text
    assert "2026-11-08" not in text and "T09:00" not in text and "这项选择作于" not in text
    assert "保留 Markdown 作为笔记格式" in text


def test_an_agent_mailbox_is_the_persons_agent_and_the_owners_own_address_is_never_theirs(reader):
    """#3164: the 账号 row listed an agent mailbox as the person's account, and an owner's own address can appear."""
    open_page, _ = reader
    page = open_page("r=" + MARA.replace("/", "%2F"), width=1440, language="en")
    owner_address = page.evaluate("""() => {
      const owner = byPath(REM.owner);
      const mine = (/[\\w.+-]+@[\\w.-]+\\.\\w+/.exec(owner?.text || '') || ['owner@self.example'])[0];
      const r = byPath('people/mara-ostrowski.md');
      r.text = r.text.replace(/^- Handles:[^\\n]*/m, '- Handles: 0xab12cd34ef@mail.openonion.ai; ' + mine);
      KNOWN.clear(); FACTS.clear(); render();
      return mine;
    }""", isolated_context=False)
    card = page.locator(".person-head .pcard")
    rows = {row.locator(".pc-k").inner_text(): row.locator(".pc-v").inner_text() for row in card.locator(".pc-row").all()}
    assert "Their agent" in rows and "0xab12cd34ef@mail.openonion.ai" in rows["Their agent"]
    assert not any("0xab12cd34ef" in value for key, value in rows.items() if key != "Their agent")
    if owner_address != "owner@self.example":
        assert owner_address not in card.inner_text()
