"""A private relation reason, and every other line drawn outside the page prose, is curtained like a passage (#3425).

The 20:25 gated hunt (2026-11-23, rc23) counted privacy per component on the three most-marked real pages: every
prose curtain worked, but a 关联 card's reason line (``span.relation-basis.private``) showed its whole private sentence
at the default 遮敏感, raw ``[sensitive]`` mark included. The card drew the reason as plain text, so the mark printed,
and its ``.private`` carried no level, so ``applyPrivacy`` (which curtains only a labelled passage) passed it by.

A second, smaller leak: a lone mark next to a citation chip, even at 只看公开.

The fixture carries real marks (the hunt noted the shared fixture had none, so a dry run proved nothing about
curtains): a sensitive relation reason, a personal one, a marked line naming another page from a knowledge topic,
a mark right before a citation, and a searchable private word. Everything is invented.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures"))

pytestmark = pytest.mark.skipif(os.environ.get("CO_REM_BROWSER_TEST") != "1",
                                reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome")

BASE = "http://rem.test/"
SHOTS = Path(os.environ.get("REM_PR_SHOTS", "/tmp/rem-3425-shots"))
ORG = "orgs/quillmere-labs-3425aaaa01.md"
PERSON = "people/tamsin-vale-3425bbbb02.md"
TOPIC = "knowledge/harbour-pilot-3425cccc03.md"
SOURCES = "\n## Sources\n- [1] gmail:fixture:9 — 2026-09-01\n- [2] gmail:fixture:9 — 2026-09-01\n"
# Private words the page must never show at 遮敏感 or 只看公开. Each is unique to one marked passage.
SENSITIVE = ["zephyrcove", "quartzledger", "marrowfen"]
PERSONAL = ["thistlebrook"]
TOKENS = ["[sensitive]", "[personal]", "［sensitive］", "［personal］"]


def _notebook(root, now):
    from rem_reader_notebook import build

    from connectonion.rem.files import Notebook
    build(root, now)
    book = Notebook(root)
    book.write(ORG, "# Quillmere Labs\n\n## Facts\n- Kind: company [1]\n\n## People\n"
               f"- [[{PERSON}]] handles the zephyrcove settlement for us [sensitive] [1]\n"
               f"- [[{TOPIC}]] is where the thistlebrook family loan sits [personal] [2]\n" + SOURCES)
    book.write(PERSON, "# Tamsin Vale\n\n## Facts\n- Email: tamsin@quillmere.test [1]\n"
               f"- Company: [[{ORG}]] [1]\n\n## Notes\n- The audit found the quartzledger gap [sensitive] [2].\n"
               "- She leads the harbour pilot. [1]\n" + SOURCES)
    book.write(TOPIC, "# Harbour pilot\n\n## Notes\n"
               f"- [[{PERSON}]] raised the marrowfen dispute in the pilot [sensitive] [1]\n" + SOURCES)
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


def _show(tab, hash_, level):
    tab.evaluate("(level) => setPrivacy(level, { save: false })", level, isolated_context=False)
    tab.evaluate("(hash) => { location.hash = hash; }", hash_, isolated_context=False)
    tab.locator("#main h1, #main .hits, #main .search-empty").first.wait_for()
    tab.wait_for_timeout(300)
    # Every fold open: a reason hidden behind a closed <details> is still in the DOM a screen reader reads.
    # A fold that holds controls (the 调查 options) stays shut: it holds no page words.
    tab.evaluate("() => document.querySelectorAll('#main details').forEach(d => { if (!d.querySelector('button, [role=menuitem], [role=menuitemradio]')) d.open = true; })", isolated_context=False)
    tab.wait_for_timeout(200)


# Visible text plus every title and aria-label: a curtain's words may sit in the DOM, never on screen or in a label.
READ = r"""() => {
  const main = document.querySelector('#main');
  const seen = [];
  const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const host = n.parentElement;
    if (!host || host.closest('[hidden], script, style')) continue;
    // A curtain hides its words by painting over them: they are not readable until lifted.
    if (host.closest('.curtain:not(.lifted)')) continue;
    const s = getComputedStyle(host);
    if (s.display === 'none' || s.visibility === 'hidden') continue;
    seen.push(n.textContent);
  }
  for (const el of main.querySelectorAll('[title], [aria-label]')) seen.push(el.getAttribute('title') || '', el.getAttribute('aria-label') || '');
  return seen.join('\n');
}"""

PAGES = [("#r=" + quote(ORG, safe=""), "org"), ("#r=" + quote(PERSON, safe=""), "person"),
         ("#r=" + quote(TOPIC, safe=""), "topic"), ("#q=" + quote("settlement"), "search")]


@pytest.mark.parametrize("hash_,name", PAGES)
@pytest.mark.parametrize("level", ["cover", "public"])
def test_no_private_words_or_raw_marks_show_outside_the_curtain(page, hash_, name, level):
    _show(page, hash_, level)
    text = page.evaluate(READ, isolated_context=False).lower()
    if level == "cover" and name == "org":
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"org-cover-{page.width}.png"), full_page=True)
    assert not [t for t in TOKENS if t in text], "a raw privacy mark never prints"
    leaked = [w for w in SENSITIVE if w in text]
    assert not leaked, f"{name} at {level}: sensitive words shown {leaked}"
    if level == "public":
        assert not [w for w in PERSONAL if w in text], f"{name}: a personal passage leaves the page at 只看公开"


def test_a_sensitive_relation_reason_is_a_curtain_bar_in_place(page):
    _show(page, "#r=" + quote(ORG, safe=""), "cover")
    reasons = page.evaluate("""() => [...document.querySelectorAll('#main .relation-basis')].map(n => ({
      curtain: n.classList.contains('curtain'), level: n.dataset.level || '', text: n.textContent }))""",
                            isolated_context=False)
    sensitive = [r for r in reasons if "zephyrcove" in r["text"]]
    assert sensitive, reasons
    assert all(r["curtain"] and r["level"] == "sensitive" for r in sensitive), sensitive
    assert not any(t in r["text"] for r in reasons for t in TOKENS), "the reason's words carry no mark"


@pytest.mark.parametrize("hash_,name", PAGES[:3])
def test_at_show_all_the_words_read_without_a_raw_mark(page, hash_, name):
    _show(page, hash_, "all")
    text = page.evaluate(READ, isolated_context=False)
    assert not [t for t in TOKENS if t in text], f"{name}: the mark is a label, not a word, even at 全部显示"
