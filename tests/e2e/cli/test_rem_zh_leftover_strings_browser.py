"""A Chinese reader shows no bare English in its own chrome, and curtains a privacy mark at either end of a line (#3410).

The art director's review of #3409 (2026-11-23) found English left in a Chinese reader on an org page:
「Parent: 课程 1234」 above the facts card, 「仍不明确：Who they are.」, an English 「如何认识」 sentence, the role
「team member」, and citation aria-labels reading "Source: …". The 11:25 hunt confirmed them live.

Two kinds of English are different problems:
- UI chrome (labels, buttons, headings, aria-labels, titles) is the reader's own text: every word goes through t().
- Prose the page skill wrote in English (an open question, how you know someone, a role) is the page's content. The
  reader never machine-translates it. When the page has a translation it shows that; when it has none, it shows the
  English inside a quiet 「原文」 quote, so it reads as quoted source and not as a Chinese label's broken half.

The scan is of the chrome only: page prose (``.prose``, ``.said``, ``blockquote``, the 原文 quote) is content.
Proper nouns and code (the fixture's invented names, domains, emails) are allowed.
The notebook is the invented one in tests/fixtures/rem_reader_notebook.py; nothing here is real.
"""
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
SHOTS = Path(os.environ.get("REM_PR_SHOTS", "/tmp/rem-zh-leftover-shots"))
UNI, COURSE, TEAM = "orgs/example-edu-1a2b3c4d.md", "orgs/1234-c0ffee1234.md", "orgs/1234-t1a-pear-c0ffeeaaaa.md"
PERSON = "people/wren-pike-zh.md"
SOURCES = "\n## Sources\n- [1] gmail:fixture:9 — 2026-09-01\n- [2] gmail:fixture:9 — 2026-09-01\n"
# Words a Chinese reader may show in Latin letters: invented proper nouns, products, file kinds and codes.
ALLOWED = {"REM", "Codex", "Claude", "WeChat", "Gmail", "Outlook", "Markdown", "Wren", "Pike", "Example", "University",
           "Lantern", "Swift", "PEAR", "edu", "com", "org", "http", "https", "www", "Kit", "Brennan", "Fernhill",
           "Labs", "Mara", "Quill", "Ash", "Kiln", "Bellwether", "Aurora", "Orchard", "Halvorsen", "Inès", "Beacon",
           "Harbor", "Alder", "Pilot", "pilot", "fixture", "gmail", "outlook", "AI", "API", "PDF", "URL", "UTC"}
# Text the scan reads: visible chrome, plus every title and aria-label. Page prose is content, not chrome.
SCAN = r"""() => {
  // The page body (.note) is the page's own words; its 「仍不明确：…」 line is the reader's and is scanned.
  const content = '.note, .orig-quote, blockquote, pre, code';
  const inContent = el => el.closest(content) && !el.closest('.unfilled-sections');
  // English the reader shows as the page's quoted original may also stand in that row's aria-label.
  const quoted = new Set([...document.querySelectorAll('#main .orig-quote')].flatMap(q => q.textContent.match(/[A-Za-z][A-Za-z'’-]{2,}/g) || []));
  const words = [];
  const add = (text, where) => {
    // Paths, addresses and domains are code, not words. Quoted words are allowed only in a label, never as visible text.
    const plain = (text || '').replace(/\S*(?:@|\/|\.md\b|\.(?:edu|com|org|net|io)\b)\S*/g, ' ');
    for (const w of plain.match(/[A-Za-z][A-Za-z'’-]{2,}/g) || []) if (where.startsWith('text:') || !quoted.has(w)) words.push([w, where, (text || '').slice(0, 80)]);
  };
  const walker = document.createTreeWalker(document.querySelector('#main') || document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const host = node.parentElement;
    if (!host || inContent(host) || host.closest('[hidden], script, style')) continue;
    const style = getComputedStyle(host);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    add(node.textContent, 'text:' + host.tagName.toLowerCase() + '.' + (host.className || ''));
  }
  for (const el of (document.querySelector('#main') || document.body).querySelectorAll('[aria-label], [title]')) {
    if (inContent(el)) continue;
    add(el.getAttribute('aria-label'), 'aria:' + el.tagName.toLowerCase());
    add(el.getAttribute('title'), 'title:' + el.tagName.toLowerCase());
  }
  return words;
}"""


def _notebook(root, now):
    from rem_reader_notebook import build
    from connectonion.rem.files import Notebook
    build(root, now)
    book = Notebook(root)
    book.write(UNI, "# Example University\n\n## Domains\n- example.edu\n\n## Facts\n- Kind: university [1]\n" + SOURCES)
    book.write(COURSE, "# 1234\n\n## Domains\n- Unknown\n\n## Facts\n- Kind: course [1]\n"
               f"- Parent: [[{UNI}]] [2]\n- What they do: Unknown\n" + SOURCES)
    # The team carries what the hunt saw: an English open question, an English role and an English "how we know them".
    book.write(TEAM, "# 1234-T1A-PEAR\n\n## Domains\n- Unknown\n\n## Facts\n- Kind: 团队 [1]\n"
               f"- Parent: [[{COURSE}]] [2]\n- To you: 你带的课程小组 [1]\n- You are: team member [2]\n"
               "- What they do: 课程项目小组 [1]\n\n## Open questions\n- Who they are. [1]\n" + SOURCES)
    book.write(PERSON, "# Wren Pike\n\n## Facts\n- Email: wren@example.edu [1]\n- Role: team member [2]\n"
               "- How we know them: Met through the course pilot. [1]\n"
               "- Company: [[" + TEAM + "]] [1]\n\n## Notes\n- [sensitive] Leading mark: private detail about health. [1]\n"
               "- Trailing mark: another private detail [sensitive] [2]\n" + SOURCES)
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
    from urllib.parse import quote
    tab.evaluate("(hash) => { location.hash = hash; }", "#r=" + quote(record, safe=""), isolated_context=False)
    tab.locator("#main h1").first.wait_for()
    tab.wait_for_timeout(300)
    # Every fold open, so nothing English hides behind a <details>.
    tab.evaluate("() => document.querySelectorAll('#main details').forEach(d => { d.open = true; })", isolated_context=False)
    tab.wait_for_timeout(150)


def _english(tab):
    words = tab.evaluate(SCAN, isolated_context=False)
    return [(w, where, text) for w, where, text in words if w not in ALLOWED and not re.fullmatch(r"[A-Z0-9-]+", w)]


@pytest.mark.parametrize("record", [TEAM, COURSE, PERSON])
def test_a_chinese_reader_shows_no_english_chrome(page, record):
    _open(page, record)
    found = _english(page)
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{Path(record).stem}-{page.width}.png"), full_page=False)
    assert not found, found[:12]


def test_english_page_prose_reads_as_quoted_original(page):
    """「仍不明确：Who they are.」 and the English role/how-we-met lines show as a quiet 原文 quote, never as bare English
    after a Chinese label, and the reader never invents a translation."""
    for record in (TEAM, PERSON):
        _open(page, record)
        bare = page.evaluate(r"""() => [...document.querySelectorAll('#main *')]
          .filter(el => el.children.length === 0 && !el.closest('.orig-quote')
            && /[一-鿿][：:]\s*[A-Za-z][a-z'’-]*\s+[a-z]{2,}/.test(el.textContent))
          .map(el => el.textContent.slice(0, 60))""", isolated_context=False)
        assert not bare, bare
        if record == PERSON:  # the team page has no English sentence left: its role and section name are labels
            quoted = page.evaluate("() => [...document.querySelectorAll('#main .orig-quote')].map(q => q.textContent)",
                                   isolated_context=False)
            assert any(re.search(r"[A-Za-z]{3,}", q) for q in quoted), "the English stays readable, as the original"


def test_a_privacy_mark_at_the_start_of_a_line_is_curtained_like_one_at_the_end(page):
    _open(page, PERSON)
    text = page.evaluate("() => document.querySelector('#main').innerText", isolated_context=False)
    assert "[sensitive]" not in text and "［sensitive］" not in text, "the raw mark never shows"
    assert "private detail about health" not in text, "a leading mark curtains its line at the default level"
    assert "another private detail" not in text, "a trailing mark still curtains its line"


def test_a_mostly_chinese_line_never_carries_the_original_mark_and_a_leaked_section_name_is_translated(page):
    """Art director on #3416: 「原文 Who they are. 你带的课程小组。…」 marked a line of the reader's own Chinese, and
    "Who they are." was a section name that leaked into the summary, not the page's prose."""
    _open(page, TEAM)
    opening = page.evaluate("() => { const p = document.querySelector('#main .ov-opening'); return p ? "
                            "{text: p.textContent, quoted: p.querySelectorAll('.orig-quote').length} : null; }",
                            isolated_context=False)
    assert opening and opening["quoted"] == 0, opening
    assert "Who they are" not in opening["text"] and "他们是谁" in opening["text"], opening["text"]


def test_a_role_is_a_label_said_in_chinese_and_only_a_sentence_is_quoted_as_original(page):
    """Art director on #3416: a role ("team member") is a label from the reviewed table (团队成员), never 原文; a
    sentence ("Met through the course pilot.") keeps 原文."""
    _open(page, PERSON)
    role = page.evaluate("() => document.querySelector('#main .dek-role')?.textContent || ''", isolated_context=False)
    assert "团队成员" in role and "team member" not in role and "原文" not in role, role
    quoted = page.evaluate("() => [...document.querySelectorAll('#main .orig-quote')].map(q => q.textContent)",
                           isolated_context=False)
    # The citation tail can split one quote into two nodes; read them together.
    assert "Met through the course pilot" in " ".join(" ".join(quoted).split()), quoted
    assert not any("team member" in q for q in quoted), quoted
    _open(page, TEAM)
    tree = page.evaluate("() => [...document.querySelectorAll('#main .ov-tk')].map(n => n.textContent)", isolated_context=False)
    assert "团队成员" in tree and not any("team member" in n or "原文" in n for n in tree), tree


def test_section_headings_relation_lines_and_your_role_read_in_chinese_without_a_stray_original_mark(page):
    """The rest of the art director's #3416 review: a known body heading ("Open questions") reads in Chinese and keeps
    its English as the anchor; a relation line that now says 「上级组织：…」 carries no 原文; 「你的身份」 is a label."""
    _open(page, TEAM)
    heading = page.evaluate("() => { const h = [...document.querySelectorAll('#main .note h2')].find(h => h.dataset.anchor === 'Open questions');"
                            " return h ? {text: h.textContent, id: h.id} : null; }", isolated_context=False)
    assert heading and heading["text"].startswith("未解问题") and heading["id"].startswith("open-questions"), heading
    cards = page.evaluate("() => [...document.querySelectorAll('#main .relation-card')].map(c => c.textContent)", isolated_context=False)
    assert any("上级组织" in c for c in cards) and not any("原文" in c for c in cards), cards
    row = page.evaluate("() => { const dt = [...document.querySelectorAll('#main dt')].find(d => d.textContent.trim() === '你的身份');"
                        " return dt ? dt.nextElementSibling.textContent : null; }", isolated_context=False)
    assert row and "团队成员" in row and "team member" not in row and "原文" not in row, row
