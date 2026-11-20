"""The seams the rc35/rc36 text fixes left, closed (#3165 rc35 hunt, #3142, #3131).

- A date takes its own sentence's language, not its block's: an org summary's English sentence beside a Chinese one
  read "hosted the pilot (8月10日)".
- A labelled passage taken out at Public only (or by `unlabelled` for a summary line) left the next English sentence
  starting lowercase: "…classes. it will close".
- A citation stripped from a related-page card's line left "at Fernhill ." behind.
- A person's role and place come from the page's Chinese version when there is one, in the header and the card.
- Words on a record page are at the 13px floor at least (--s-ui): cite labels, eyebrows, relation kinds, heading
  anchors and panel labels sat at the 11px caption size, 50-170 nodes a page. Graph labels, an org's one-letter mark
  and a privacy badge are captions and may stay smaller.
"""

import os
import re
from pathlib import Path

import pytest

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.reader import write_reader

pytestmark = pytest.mark.skipif(
    os.environ.get("CO_REM_BROWSER_TEST") != "1",
    reason="opt in with CO_REM_BROWSER_TEST=1; requires installed Chrome",
)

MAIL = "gmail:18f0aa11bb22cc33dd44ee55"
PAGES = {
    "orgs/fernhill.md": (
        "# Fernhill\n\nFernhill hosted the pilot on 2026-08-10. 合同在 2026-09-01 签了 [1]。\n\n"
        "## Who they are\nThey run classes. Funding ends in May [sensitive], it will close after the term [1].\n\n"
        "## Sources\n- [1] " + MAIL + " — 2026-08-10\n"
    ),
    "people/wren-hale.md": (
        "# Wren Hale\n\nWren runs the venue at [Fernhill](../orgs/fernhill.md) [1].\n\n"
        "## Facts\n- Company: [Fernhill](../orgs/fernhill.md)\n- Role: Partner\n- Location: San Francisco Bay Area\n"
        "- Email: wren@fernhill.example (work)\n\n"
        "## Who they are\nWren runs it [1].\n\n## Sources\n- [1] " + MAIL + " — 2026-08-10\n"
    ),
    "projects/pilot.md": (
        "# Pilot\n\nThe pilot ran at [Fernhill](../orgs/fernhill.md) with [Wren Hale](../people/wren-hale.md) [1].\n\n"
        "## Sources\n- [1] " + MAIL + " — 2026-08-10\n"
    ),
    "skills/catalog/venue-booking.md": (
        "# Venue booking\n\nBook [Fernhill](../../orgs/fernhill.md) two weeks ahead [1].\n\n"
        "## Sources\n- [1] " + MAIL + " — 2026-08-10\n"
    ),
}
SHOTS = os.environ.get("REM_PR_SHOTS")
# Captions the visual system allows under the floor: graph labels, an org's one-letter mark, a privacy badge.
CAPTIONS = "svg, .org-mark, .privacy-tag"


def _reader(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    root = tmp_path / "rem"
    prepare(root)
    for record, text in PAGES.items():
        Notebook(root).write(record, text)
    return write_reader(root)


def _open(page, path, record, language):
    page.goto(path.as_uri() + "#r=" + record.replace("/", "%2F"))
    page.evaluate("language => setInterfaceLanguage(language)", language, isolated_context=False)
    page.locator("#main h1").first.wait_for()


def _text(page, selector="#main"):
    return re.sub(r"\s+", " ", page.locator(selector).first.inner_text())


@pytest.mark.parametrize("language", ["zh", "en"])
def test_a_date_takes_its_own_sentences_language(tmp_path, monkeypatch, language):
    from patchright.sync_api import sync_playwright

    path = _reader(tmp_path, monkeypatch)
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        _open(page, path, "orgs/fernhill.md", language)
        text = _text(page)
        # The same words whichever interface language is on: English sentence, English date; Chinese, Chinese.
        assert re.search(r"hosted the pilot on (Aug 10|10 Aug)\b", text), text
        assert "合同在 9月1日 签了" in text, text
        assert "pilot on 8月10日" not in text
        browser.close()


def test_a_cut_passage_leaves_the_next_english_sentence_capitalised(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright

    path = _reader(tmp_path, monkeypatch)
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        _open(page, path, "orgs/fernhill.md", "en")
        # A summary line is made by unlabelled(): mended where the passage stood.
        cut = page.evaluate("""() => [unlabelled('They run classes. Funding ends in May [sensitive], it will close.'),
          unlabelled('Funding ends in May [sensitive], it will close.'), unlabelled('Wren met them in May [personal].'),
          unlabelled('一句。资金五月到期 [sensitive]，课会停。')]""", isolated_context=False)
        assert cut[0] == "They run classes. It will close.", cut
        assert cut[1] == "It will close.", cut
        assert cut[2] == "", cut
        assert "课会停" in cut[3] and "\u0006" not in cut[3], cut
        # Public only takes the passage out of the page: the sentence after it starts with a capital.
        page.evaluate("setPrivacy('public')", isolated_context=False)
        text = _text(page)
        assert "Funding ends" not in text, text
        assert re.search(r"classes\. It will close after the term", text), text
        if SHOTS:
            page.screenshot(path=str(Path(SHOTS) / "text-seams-public-1440.png"), full_page=True)
        browser.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_a_related_cards_line_has_no_space_before_its_full_stop(tmp_path, monkeypatch, width):
    from patchright.sync_api import sync_playwright

    path = _reader(tmp_path, monkeypatch)
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": width, "height": 900 if width > 400 else 844})
        _open(page, path, "people/wren-hale.md", "en")
        page.evaluate("document.querySelectorAll('#main details').forEach(d => d.open = true)", isolated_context=False)
        bases = page.locator("#main .relation-basis").all_inner_texts()
        assert bases, "the fixture links the person from two pages"
        assert not [b for b in bases if re.search(r"\s[.,;:!?]", b)], bases
        assert any(b.endswith("at Fernhill with Wren Hale.") for b in bases), bases
        browser.close()


def test_role_and_place_read_from_the_chinese_version(tmp_path, monkeypatch):
    from patchright.sync_api import sync_playwright

    path = _reader(tmp_path, monkeypatch)
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        _open(page, path, "people/wren-hale.md", "zh")
        page.evaluate("""() => { const r = byPath('people/wren-hale.md');
          r.translations = { zh: r.text.replace('Role: Partner', 'Role: 合伙人').replace('Location: San Francisco Bay Area', 'Location: 旧金山湾区') };
          KNOWN.clear(); FACTS.clear(); PARSED_FACTS.clear(); render(); }""", isolated_context=False)
        head = _text(page, "#main")
        assert "合伙人" in head and "旧金山湾区" in head, head
        assert "Partner" not in head and "Bay Area" not in head, head
        browser.close()


@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize("width", [1440, 390])
def test_words_on_a_record_page_are_at_the_floor(tmp_path, monkeypatch, language, width):
    from patchright.sync_api import sync_playwright

    path = _reader(tmp_path, monkeypatch)
    with sync_playwright() as api:
        browser = api.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": width, "height": 900 if width > 400 else 844})
        for record in PAGES:
            _open(page, path, record, language)
            page.evaluate("document.querySelectorAll('#main details').forEach(d => d.open = true)", isolated_context=False)
            small = page.evaluate("""captions => { const out = [], walker = document.createTreeWalker(document.getElementById('main'), NodeFilter.SHOW_TEXT);
              for (let n = walker.nextNode(); n; n = walker.nextNode()) { const p = n.parentElement;
                if (!/[\\p{L}\\p{N}]/u.test(n.nodeValue) || !p.getClientRects().length || p.closest('[hidden]') || p.closest(captions)) continue;
                if (getComputedStyle(p).visibility === 'hidden') continue;
                const size = parseFloat(getComputedStyle(p).fontSize);
                if (size < 13) out.push(p.tagName + '.' + [...p.classList].join('.') + ' ' + size + 'px: ' + n.nodeValue.trim().slice(0, 30)); }
              return out; }""", CAPTIONS, isolated_context=False)
            assert not small, (record, small[:8])
            if SHOTS and width == 1440 and language == "zh" and record == "people/wren-hale.md":
                page.screenshot(path=str(Path(SHOTS) / "text-seams-person-zh-1440.png"), full_page=True)
            if SHOTS and width == 390 and language == "zh" and record == "orgs/fernhill.md":
                page.screenshot(path=str(Path(SHOTS) / "text-seams-org-zh-390.png"), full_page=True)
        browser.close()
