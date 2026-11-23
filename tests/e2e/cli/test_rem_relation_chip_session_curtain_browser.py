"""A relation card carries the same privacy chip as the line it quotes, and a session turn whose heading carries a
privacy level is curtained, with its words still drawn literally inside (#3425 follow-up).

After #3427 a relation reason drew its words without the raw mark, but also without the 「私人」 / 「敏感」 chip the same
sentence carries in the body and the 关联 list. The card now builds the chip from the same level data.

A session's "What you typed" quote is the owner's own typing, kept literally, a typed "[personal]" included
(test_rem_sessions pins that). Its privacy level comes from the page's structure instead: the turn's own heading,
"### 09:12 [sensitive]". That heading level used to reach neither the reader nor the server's session_detail, so the
turn showed in full at 遮敏感 and reached a shared reader. Everything here is invented.
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
SHOTS = Path(os.environ.get("REM_PR_SHOTS", "/tmp/rem-chip-shots"))
ORG = "orgs/quillmere-labs-3425aaaa01.md"
PERSON = "people/tamsin-vale-3425bbbb02.md"
TOPIC = "knowledge/harbour-pilot-3425cccc03.md"
SESSION = "sessions/codex-3425-quiet.md"
SOURCES = "\n## Sources\n- [1] gmail:fixture:9 — 2026-09-01\n- [2] gmail:fixture:9 — 2026-09-01\n"


def _notebook(root, now):
    from rem_reader_notebook import build

    from connectonion.rem.files import Notebook
    build(root, now)
    book = Notebook(root)
    book.write(ORG, "# Quillmere Labs\n\n## Facts\n- Kind: company [1]\n\n## People\n"
               f"- [[{PERSON}]] handles the zephyrcove settlement for us [sensitive] [1]\n"
               f"- [[{TOPIC}]] is where the thistlebrook family loan sits [personal] [2]\n" + SOURCES)
    book.write(PERSON, "# Tamsin Vale\n\n## Facts\n- Email: tamsin@quillmere.test [1]\n"
               f"- Company: [[{ORG}]] [1]\n" + SOURCES)
    book.write(TOPIC, "# Harbour pilot\n\n## Notes\n- The pilot runs weekly. [1]\n" + SOURCES)
    book.write(SESSION, "# Quiet session\n\n## Facts\n- Date: 2026-09-30\n- Agent: Codex\n- Project: scratch\n"
               "- Folder: /work/scratch\n- Session: codex-3425-quiet\n- Turns: 2\n\n## What you typed\n"
               "### 09:12 [sensitive]\n> plan the brackenhold move before anyone hears\n"
               "### 09:20\n> keep this literal [personal] as I typed it\n\n## Final reply\n> Done.\n\n"
               "## Sources\n- codex:fixture:1\n- codex:fixture:2\n")
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


def _show(tab, record, level):
    tab.evaluate("(level) => setPrivacy(level, { save: false })", level, isolated_context=False)
    tab.evaluate("(hash) => { location.hash = hash; }", "#r=" + quote(record, safe=""), isolated_context=False)
    tab.locator("#main h1").first.wait_for()
    tab.wait_for_timeout(300)
    tab.evaluate("() => document.querySelectorAll('#main details').forEach(d => { if (!d.querySelector('button, [role=menuitem], [role=menuitemradio]')) d.open = true; })", isolated_context=False)
    tab.wait_for_timeout(200)


CARDS = """() => [...document.querySelectorAll('#main .relation-basis')].map(n => ({
  text: n.textContent, level: n.dataset.level || '', chips: [...n.querySelectorAll('.privacy-tag')].map(c => c.className),
  curtain: n.classList.contains('curtain') }))"""


@pytest.mark.parametrize("level", ["all", "cover"])
def test_a_relation_reason_carries_the_same_privacy_chip_as_the_line_it_quotes(page, level):
    _show(page, ORG, level)
    if level == "all":
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"org-all-{page.width}.png"), full_page=True)
    cards = page.evaluate(CARDS, isolated_context=False)
    personal = [c for c in cards if "thistlebrook" in c["text"]]
    assert personal and all(any("personal" in k for k in c["chips"]) for c in personal), cards
    if level == "all":
        sensitive = [c for c in cards if "zephyrcove" in c["text"]]
        assert sensitive and all(any("sensitive" in k for k in c["chips"]) for c in sensitive), cards
    else:
        assert all(c["curtain"] for c in cards if c["level"] == "sensitive"), cards


QUOTES = """() => [...document.querySelectorAll('#main .session-quote')].map(q => ({
  text: q.textContent, level: q.dataset.level || q.closest('[data-level]')?.dataset.level || '',
  curtained: !!q.closest('.curtain:not(.lifted)'), shown: !!(q.offsetWidth || q.offsetHeight) }))"""


def test_a_session_turn_whose_heading_carries_a_level_is_curtained_with_its_words_literal(page):
    _show(page, SESSION, "cover")
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"session-cover-{page.width}.png"), full_page=True)
    quotes = page.evaluate(QUOTES, isolated_context=False)
    marked = [q for q in quotes if "brackenhold" in q["text"]]
    assert marked, quotes
    assert all(q["curtained"] and q["level"] == "sensitive" for q in marked), marked
    assert all(q["text"] == "plan the brackenhold move before anyone hears" for q in marked), "words stay literal"
    typed = [q for q in quotes if "keep this literal" in q["text"]]
    assert typed and all("[personal]" in q["text"] for q in typed), "a typed token stays as typed"
    times = page.evaluate("() => [...document.querySelectorAll('#main time, #main h3')].map(t => t.textContent)",
                          isolated_context=False)
    assert not any("[sensitive]" in t for t in times), times
    _show(page, SESSION, "public")
    gone = page.evaluate(QUOTES, isolated_context=False)
    assert not [q for q in gone if "brackenhold" in q["text"] and q["shown"]], gone


def test_a_shared_reader_never_receives_a_turn_whose_heading_is_marked():
    from connectonion.rem.reader_model import session_detail
    page = ("# S\n\n## What you typed\n### 09:12 [sensitive]\n> plan the brackenhold move\n### 09:20\n> plain words\n\n"
            "## Final reply\n> Done.\n")
    shared = session_detail(page, private=False)["session_messages"]
    assert not any("brackenhold" in m["text"] for m in shared), shared
    own = session_detail(page, private=True)["session_messages"]
    turn = next(m for m in own if "brackenhold" in m["text"])
    assert turn["level"] == "sensitive" and turn["time"] == "09:12", turn
