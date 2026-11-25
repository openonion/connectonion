"""A facts card never breaks a short value one character per line, and speaks the reader's language (#3405).

The 08:25 hunt on rc20 (2026-11-23): a team org's facts card (资料) set its Kind value as 「团」 over 「队」, because
the label column took the card's width and the value cell shrank to one CJK character. Its labels were English
(Kind, Parent) in a Chinese reader: those two had no entry in the reader's table. The card is shared by person, org
and project pages, so each is checked at 1440 and 390, in Chinese. The notebook is the invented one in
tests/fixtures/rem_reader_notebook.py, with a university, a course and a team under it.
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
SHOTS = Path(os.environ.get("REM_PR_SHOTS", "/tmp/rem-facts-card-shots"))
UNI, COURSE, TEAM = "orgs/example-edu-1a2b3c4d.md", "orgs/1234-c0ffee1234.md", "orgs/1234-t1a-pear-c0ffeeaaaa.md"
PROJECT = "projects/lantern-cjk.md"
SOURCES = "\n## Sources\n- [1] gmail:fixture:9 — 2026-09-01\n- [2] gmail:fixture:9 — 2026-09-01\n"
# Every English label a facts card can show: the three kinds' fixed lists and the extra lines page skills write.
LABELS = ["Email", "Phone", "Company", "Role", "Location", "Time zone", "Links", "How we know them", "First contact",
          "Last contact", "Signing entity", "Handles", "Language", "Also known as", "Repository", "Stack", "Status",
          "People", "Organisation", "Started", "Last activity", "What they do", "Website", "Legal entity",
          "Your contacts", "Kind", "Parent", "To you", "You are", "Unit", "Role in unit", "Mail"]


def _notebook(root, now):
    from rem_reader_notebook import build
    from connectonion.rem.files import Notebook
    build(root, now)
    book = Notebook(root)
    book.write(UNI, "# Example University\n\n## Domains\n- example.edu\n\n## Facts\n- Kind: university [1]\n" + SOURCES)
    book.write(COURSE, "# 1234\n\n## Domains\n- Unknown\n\n## Facts\n- Kind: course [1]\n"
               f"- Parent: [[{UNI}]] [2]\n- What they do: Unknown\n" + SOURCES)
    book.write(TEAM, "# 1234-T1A-PEAR\n\n## Domains\n- Unknown\n\n## Facts\n- Kind: 团队 [1]\n"
               f"- Parent: [[{COURSE}]] [2]\n- To you: 你带的课程小组 [1]\n- You are: 导师 [2]\n"
               "- What they do: 课程项目小组 [1]\n\n## Who they are\n- Unknown — not investigated yet\n" + SOURCES)
    # A project with short CJK facts and a linked organisation, so the shared card is checked on a project too.
    book.write(PROJECT, "# 灯塔\n\n## Facts\n- Status: 进行中 [1]\n- Stack: Swift [2]\n"
               f"- Organisation: [[{COURSE}]] [1]\n- Started: 2026-09-01 [2]\n" + SOURCES)
    return root


@pytest.fixture(params=[1440, 390])
def page(request, tmp_path, monkeypatch):
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

    width = request.param
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": width, "height": 900 if width > 500 else 844}, locale="zh-CN",
                                      reduced_motion="reduce", is_mobile=width < 500, has_touch=width < 500)
        tab = context.new_page()
        tab.on("pageerror", lambda error: errors.append(str(error)))
        context.route("http*://**/*", serve)
        tab.goto(BASE)
        tab.locator("#main h1, .night-card").first.wait_for()
        tab.evaluate("() => setInterfaceLanguage('zh')", isolated_context=False)
        tab.width = width
        yield tab
        browser.close()
    assert not errors, errors


def _open(tab, record):
    tab.evaluate("(where) => { location.hash = href(byPath(where)).slice(1); render(); }", record, isolated_context=False)
    tab.locator(".factlist").first.wait_for()
    tab.wait_for_timeout(200)


# For each value cell: its own width and the width of three CJK characters in its font.
CELLS = """() => [...document.querySelectorAll('.factlist dd')].filter(dd => dd.offsetParent).map(dd => {
  const probe = document.createElement('span'); probe.textContent = '团队名';
  probe.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;font:' + getComputedStyle(dd).font;
  document.body.appendChild(probe); const three = probe.getBoundingClientRect().width; probe.remove();
  return { text: dd.innerText.trim().slice(0, 20), width: dd.getBoundingClientRect().width, three };
})"""


@pytest.mark.parametrize("record", [TEAM, COURSE, PROJECT])
def test_a_facts_value_cell_is_never_narrower_than_three_characters(page, record):
    _open(page, record)
    cells = page.evaluate(CELLS, isolated_context=False)
    assert cells, "no facts card rendered"
    narrow = [c for c in cells if c["width"] + 0.5 < c["three"]]
    assert not narrow, narrow
    if record == TEAM:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.locator(".factlist").first.scroll_into_view_if_needed()
        page.screenshot(path=str(SHOTS / f"facts-team-{page.width}.png"))


@pytest.mark.parametrize("record", [TEAM, COURSE, PROJECT])
def test_no_facts_label_is_english_in_chinese(page, record):
    _open(page, record)
    labels = page.evaluate("() => [...document.querySelectorAll('.factlist dt')].map(dt => dt.innerText.trim())",
                           isolated_context=False)
    english = [label for label in labels if label in LABELS]
    assert not english, english


def test_every_known_facts_label_has_a_chinese_name(page):
    missing = page.evaluate("(labels) => labels.filter(label => t(label) === label)", LABELS, isolated_context=False)
    assert not missing, missing


# A value of up to 12 characters keeps its words together, and a linked value stays one link (#3405): the cite tail
# used to take the last CJK character (「团」 | 「队 9月1日」) and cut 「课程 1234」 into two links.
SPLITS = """() => [...document.querySelectorAll('.factlist dd .val')].map(val => {
  const tail = val.querySelector('.fact-tail'); const head = tail ? val.textContent.slice(0, val.textContent.indexOf(tail.textContent)) : '';
  const hrefs = [...val.querySelectorAll('a:not(.cite)')].map(a => a.getAttribute('href'));
  const bare = tail ? tail.cloneNode(true) : null; bare?.querySelectorAll('.cite').forEach(c => c.remove());
  const word = bare ? bare.textContent.trim() : '';
  return { text: val.textContent.slice(0, 30), head, word, repeated: hrefs.length !== new Set(hrefs).size };
})"""


@pytest.mark.parametrize("record", [TEAM, COURSE, PROJECT])
def test_a_short_value_is_not_cut_and_a_link_stays_one_link(page, record):
    _open(page, record)
    values = page.evaluate(SPLITS, isolated_context=False)
    assert values, "no facts values rendered"
    # A value about four characters wide moves whole; a longer one keeps at least two characters with its marks.
    short = [v for v in values if v["head"].strip() and len((v["head"] + v["word"]).strip()) <= 4]
    assert not short, short
    alone = [v for v in values if v["head"].strip() and len(v["word"]) < 2]
    assert not alone, alone
    assert not [v for v in values if v["repeated"]], values


# A label of up to six Chinese characters stays on one line (the 80px label column broke 「与你的关系」 in two).
LABEL_LINES = """() => [...document.querySelectorAll('.factlist dt')].filter(dt => dt.offsetParent).map(dt => {
  const range = document.createRange(); range.selectNodeContents(dt);
  const tops = new Set([...range.getClientRects()].map(rect => Math.round(rect.top)));
  return { text: dt.innerText.trim(), lines: tops.size };
})"""


@pytest.mark.parametrize("record", [TEAM, PROJECT])
def test_a_short_label_stays_on_one_line(page, record):
    _open(page, record)
    labels = page.evaluate(LABEL_LINES, isolated_context=False)
    broken = [label for label in labels if len(label["text"]) <= 6 and label["lines"] > 1]
    assert not broken, broken
